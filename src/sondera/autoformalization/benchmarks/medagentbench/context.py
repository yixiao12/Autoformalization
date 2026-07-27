"""Deterministic medical and trajectory-state normalization."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sondera import ToolCall, ToolOutput  # type: ignore[attr-defined]

from ...normalization import SecurityContextNormalizer

BENCHMARK_NOW = "2023-11-13T10:15:00+00:00"
BENCHMARK_DATE = "2023-11-13"
_WRITE_TOOLS = {
    "post_request",
    "post_observation",
    "post_medication_request",
    "post_service_request",
}
_RESOURCE_TO_TOOL = {
    "patient": "get_patient",
    "condition": "get_condition",
    "observation": "get_observation",
    "medicationrequest": "get_medication_request",
    "procedure": "get_procedure",
    "servicerequest": "get_service_request",
}
_ERROR_PATTERN = re.compile(
    r"\b(error|failed|failure|denied|blocked|invalid|exception|cancelled)\b",
    re.IGNORECASE,
)
_PATIENT_ID_PATTERN = re.compile(r"\bS\d{6,}\b", re.IGNORECASE)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _body(arguments: dict[str, Any]) -> dict[str, Any]:
    for key in ("observation", "medication_request", "service_request"):
        value = arguments.get(key)
        if isinstance(value, dict):
            return value
    return _json_object(arguments.get("payload"))


def _canonical_tool(tool: str, arguments: dict[str, Any]) -> str:
    if tool not in {"get_request", "post_request"}:
        return tool
    raw_url = arguments.get("url")
    if not isinstance(raw_url, str):
        return tool
    resource = urlsplit(raw_url).path.rstrip("/").rsplit("/", 1)[-1].lower()
    base = _RESOURCE_TO_TOOL.get(resource)
    if base is None:
        return tool
    return base.replace("get_", "post_", 1) if tool == "post_request" else base


def _patient_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if (
                key in {"patient_id", "id"}
                and isinstance(child, str)
                and (key == "patient_id" or child.upper().startswith("S"))
            ):
                found.add(child)
            if (
                key == "reference"
                and isinstance(child, str)
                and child.lower().startswith("patient/")
            ):
                found.add(child.split("/", 1)[1])
            found.update(_patient_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_patient_ids(child))
    elif isinstance(value, str):
        found.update(_PATIENT_ID_PATTERN.findall(value))
    return {item.upper() for item in found if item}


def _raw_query(arguments: dict[str, Any]) -> dict[str, list[str]]:
    value = arguments.get("url")
    return parse_qs(urlsplit(value).query) if isinstance(value, str) else {}


def _resource_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    body = _body(arguments)
    return body if body else arguments


def _first_text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _has_coding(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    coding = value.get("coding")
    return isinstance(coding, list) and any(isinstance(item, dict) for item in coding)


def _dates(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {
                "authoredOn",
                "issued",
                "effectiveDateTime",
                "occurrenceDateTime",
            } and isinstance(child, str):
                result.append(child)
            result.extend(_dates(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_dates(child))
    return result


def _stable_signature(tool: str, arguments: dict[str, Any]) -> str:
    serialized = json.dumps(
        arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(f"{tool}:{serialized}".encode()).hexdigest()[:24]


def empty_session_facts() -> dict[str, object]:
    """Return the complete trusted session record expected by Cedar."""
    return {
        "now_timestamp": BENCHMARK_NOW,
        "now_date": BENCHMARK_DATE,
        "last_tool_error": False,
        "last_get_patient_returned_multiple": False,
        "user_specified_urgency": False,
        "user_specified_backdate": False,
        "user_specified_correction": False,
        "user_confirmed_allergy_check": False,
        "last_assistant_restated_patient": False,
        "user_confirmed_write": False,
        "pending_write_confirmed": False,
        "current_call_is_duplicate": False,
        "current_call_retries_failed_write": False,
        "current_call_patient_mismatch": False,
        "current_call_is_backdated": False,
        "current_call_is_correction": False,
        "current_call_patient_unseen": False,
        "established_patient_id": "",
        "prior_post_signatures": [],
        "failed_post_signatures": [],
        "seen_patient_ids": [],
    }


def empty_medical_facts() -> dict[str, object]:
    """Return deterministic facts about the current FHIR tool call."""
    return {
        "canonical_tool": "",
        "is_write": False,
        "payload_present": False,
        "patient_id_present": False,
        "current_patient_id": "",
        "subject_reference_present": False,
        "subject_is_patient": False,
        "purpose_present": False,
        "purpose_is_patient_care": False,
        "query_has_identifier": False,
        "query_is_broad": False,
        "count_present": False,
        "count": 0,
        "count_is_narrow": False,
        "resource_type": "",
        "status": "",
        "intent": "",
        "priority": "",
        "resource_id_present": False,
        "medication_concept_present": False,
        "dosage_present": False,
        "authored_on_present": False,
        "issued_present": False,
        "observation_category_present": False,
        "observation_category_system_present": False,
        "observation_category_display_present": False,
        "service_request_code_present": False,
    }


@dataclass(frozen=True)
class PreparedCall:
    """Current-call facts plus state update metadata."""

    tool: str
    canonical_tool: str
    arguments: dict[str, Any]
    session: dict[str, object]
    medical: dict[str, object]
    patient_ids: frozenset[str]
    signature: str
    is_post: bool


@dataclass
class ReplayState:
    """Deterministic pre-pass state accumulated from prior trace events."""

    seen_patient_ids: set[str] = field(default_factory=set)
    established_patient_id: str = ""
    prior_post_signatures: set[str] = field(default_factory=set)
    failed_post_signatures: set[str] = field(default_factory=set)
    last_tool_error: bool = False
    last_get_patient_returned_multiple: bool = False
    user_specified_urgency: bool = False
    user_specified_backdate: bool = False
    user_specified_correction: bool = False
    user_confirmed_allergy_check: bool = False
    user_confirmed_write: bool = False
    last_assistant_restated_patient: bool = False
    pending: dict[str, PreparedCall] = field(default_factory=dict)

    def observe_user(self, content: str) -> None:
        lowered = content.lower()
        self.user_specified_urgency |= any(
            token in lowered for token in ("stat", "urgent", "immediately")
        )
        self.user_specified_backdate |= any(
            token in lowered for token in ("backdate", "back-date", "dated as")
        )
        self.user_specified_correction |= any(
            token in lowered for token in ("correct", "amend", "replace")
        )
        confirmation = lowered.strip().startswith("confirm") or "i confirm" in lowered
        self.user_confirmed_write = confirmation
        self.user_confirmed_allergy_check |= confirmation and "allerg" in lowered

    def observe_assistant(self, content: str) -> None:
        lowered = content.lower()
        has_patient = (
            bool(_PATIENT_ID_PATTERN.search(content)) or "patient id" in lowered
        )
        has_identity = has_patient and any(
            token in lowered
            for token in ("date of birth", "dob", "patient name", "mrn")
        )
        self.last_assistant_restated_patient = has_identity

    def _base_session(self) -> dict[str, object]:
        facts = empty_session_facts()
        facts.update(
            {
                "last_tool_error": self.last_tool_error,
                "last_get_patient_returned_multiple": self.last_get_patient_returned_multiple,
                "user_specified_urgency": self.user_specified_urgency,
                "user_specified_backdate": self.user_specified_backdate,
                "user_specified_correction": self.user_specified_correction,
                "user_confirmed_allergy_check": self.user_confirmed_allergy_check,
                "last_assistant_restated_patient": self.last_assistant_restated_patient,
                "user_confirmed_write": self.user_confirmed_write,
                "pending_write_confirmed": (
                    self.user_confirmed_write and self.last_assistant_restated_patient
                ),
                "established_patient_id": self.established_patient_id,
                "prior_post_signatures": sorted(self.prior_post_signatures),
                "failed_post_signatures": sorted(self.failed_post_signatures),
                "seen_patient_ids": sorted(self.seen_patient_ids),
            }
        )
        return facts

    def prepare_call(self, tool: str, arguments: Any) -> PreparedCall:
        args = _json_object(arguments)
        canonical = _canonical_tool(tool, args)
        is_post = tool in _WRITE_TOOLS or canonical.startswith("post_")
        fields = _resource_fields(args)
        query = _raw_query(args)
        patient_ids = _patient_ids(fields)
        if not patient_ids:
            for key in ("patient", "subject", "identifier"):
                patient_ids.update(value.upper() for value in query.get(key, []))
        current_patient = sorted(patient_ids)[0] if patient_ids else ""
        subject = fields.get("subject") if isinstance(fields, dict) else None
        reference = subject.get("reference") if isinstance(subject, dict) else None
        purpose = args.get("purpose")
        count = args.get("_count")
        if count is None and "_count" in query:
            try:
                count = int(query["_count"][0])
            except (ValueError, TypeError):
                count = None
        identifier_keys = {
            "patient_id",
            "birthdate",
            "family",
            "given",
            "name",
            "identifier",
        }
        query_has_identifier = any(args.get(key) for key in identifier_keys) or any(
            query.get(key) for key in identifier_keys
        )
        resource_type = _first_text(fields.get("resourceType"))
        medication = fields.get("medicationCodeableConcept")
        category = fields.get("category")
        first_category = category[0] if isinstance(category, list) and category else {}
        category_coding = (
            first_category.get("coding") if isinstance(first_category, dict) else None
        )
        first_coding = (
            category_coding[0]
            if isinstance(category_coding, list) and category_coding
            else {}
        )

        medical = empty_medical_facts()
        medical.update(
            {
                "canonical_tool": canonical,
                "is_write": is_post,
                "payload_present": bool(_body(args)),
                "patient_id_present": bool(patient_ids),
                "current_patient_id": current_patient,
                "subject_reference_present": isinstance(reference, str)
                and bool(reference),
                "subject_is_patient": isinstance(reference, str)
                and reference.lower().startswith("patient/"),
                "purpose_present": isinstance(purpose, str),
                "purpose_is_patient_care": isinstance(purpose, str)
                and purpose.lower() == "patient care",
                "query_has_identifier": query_has_identifier,
                "query_is_broad": canonical.startswith("get_")
                and not query_has_identifier
                and not patient_ids,
                "count_present": isinstance(count, int),
                "count": count if isinstance(count, int) else 0,
                "count_is_narrow": isinstance(count, int) and 0 < count <= 10,
                "resource_type": resource_type,
                "status": _first_text(fields.get("status")),
                "intent": _first_text(fields.get("intent")),
                "priority": _first_text(fields.get("priority")),
                "resource_id_present": isinstance(fields.get("id"), str)
                and bool(fields.get("id")),
                "medication_concept_present": isinstance(medication, dict)
                and (_has_coding(medication) or bool(medication.get("text"))),
                "dosage_present": isinstance(fields.get("dosageInstruction"), list)
                and bool(fields.get("dosageInstruction")),
                "authored_on_present": isinstance(fields.get("authoredOn"), str),
                "issued_present": isinstance(fields.get("issued"), str),
                "observation_category_present": bool(category),
                "observation_category_system_present": isinstance(first_coding, dict)
                and bool(first_coding.get("system")),
                "observation_category_display_present": isinstance(first_coding, dict)
                and bool(first_coding.get("display")),
                "service_request_code_present": isinstance(fields.get("code"), dict)
                and (
                    _has_coding(fields.get("code"))
                    or bool(fields.get("code", {}).get("text"))
                ),
            }
        )

        signature = _stable_signature(canonical, args)
        dated = any(value[:10] < BENCHMARK_DATE for value in _dates(fields))
        mismatch = bool(
            self.established_patient_id
            and patient_ids
            and self.established_patient_id not in patient_ids
        )
        unseen = bool(
            is_post and patient_ids and not patient_ids <= self.seen_patient_ids
        )
        session = self._base_session()
        session.update(
            {
                "current_call_is_duplicate": signature in self.prior_post_signatures,
                "current_call_retries_failed_write": signature
                in self.failed_post_signatures,
                "current_call_patient_mismatch": mismatch,
                "current_call_is_backdated": dated,
                "current_call_is_correction": bool(medical["resource_id_present"]),
                "current_call_patient_unseen": unseen,
            }
        )
        return PreparedCall(
            tool=tool,
            canonical_tool=canonical,
            arguments=args,
            session=session,
            medical=medical,
            patient_ids=frozenset(patient_ids),
            signature=signature,
            is_post=is_post,
        )

    def register_call(self, call_id: str, prepared: PreparedCall) -> None:
        self.pending[call_id] = prepared

    def session_snapshot(self) -> dict[str, object]:
        return self._base_session()

    def observe_output(self, call_id: str, content: str) -> None:
        prepared = self.pending.pop(call_id, None)
        is_error = bool(_ERROR_PATTERN.search(content))
        self.last_tool_error = is_error
        self.last_get_patient_returned_multiple = False
        if prepared is None:
            return
        parsed: Any = content
        with suppress(json.JSONDecodeError):
            parsed = json.loads(content)

        if prepared.canonical_tool == "get_patient" and not is_error:
            result: Any = parsed
            if isinstance(parsed, dict):
                result = parsed.get("result", parsed.get("entry", []))
            if isinstance(result, list):
                self.last_get_patient_returned_multiple = len(result) > 1
            ids = _patient_ids(parsed)
            self.seen_patient_ids.update(ids)
            if not self.established_patient_id and len(ids) == 1:
                self.established_patient_id = next(iter(ids))
        elif prepared.canonical_tool.startswith("get_") and not is_error:
            self.seen_patient_ids.update(prepared.patient_ids)
            if not self.established_patient_id and len(prepared.patient_ids) == 1:
                self.established_patient_id = next(iter(prepared.patient_ids))

        if prepared.is_post:
            if is_error:
                self.failed_post_signatures.add(prepared.signature)
            else:
                self.prior_post_signatures.add(prepared.signature)


class ReplayContextProvider:
    """Mutable bridge from an adapted event to generic Cedar callbacks."""

    def __init__(self) -> None:
        self._session = empty_session_facts()
        self._medical = empty_medical_facts()
        self._security = SecurityContextNormalizer()

    def set_context(
        self,
        *,
        session: dict[str, object],
        medical: dict[str, object] | None = None,
    ) -> None:
        self._session = session
        self._medical = medical or empty_medical_facts()

    def enrich_tool_call(self, call: ToolCall) -> dict[str, object]:
        return {
            "normalized": self._security.enrich(call)["normalized"],
            "medical": self._medical,
            "session": self._session,
        }

    def enrich_tool_output(self, output: ToolOutput) -> dict[str, object]:
        return {"session": self._session}
