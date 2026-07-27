"""MedAgentBench-specific context schema built on the generic Agent schema."""

from __future__ import annotations

from cedar.schema import SchemaType

from cedar import Schema
from sondera.harness.cedar.schema import agent_to_cedar_schema

from ...normalization import normalized_context_schema
from ...spec import AgentSpec, GeneratedSchema

MEDAGENT_CONTEXT_GUIDE = """Trusted MedAgentBench replay context is generated
deterministically from the current FHIR call and prior recorded events.
`context.medical` describes the current call: canonical_tool maps raw HTTP calls
to typed FHIR operations; is_write identifies POST operations; patient, purpose,
query width, subject linkage, status/intent/priority, medication/dosage, and FHIR
shape booleans are normalized facts. `context.session` describes prior-event
state and current-call comparisons: patient history, explicit confirmation,
patient restatement, duplicate/failed writes, wrong-patient calls, backdating,
corrections, allergy confirmation, and previous tool errors. These records are
trusted runtime facts. Guard them with `context has medical/session` and prefer
them over raw-string `like` expressions. Empty strings and empty sets mean the
fact has not been established.
"""


def _record(boolean_fields: set[str], string_fields: set[str]) -> SchemaType:
    attributes = {name: SchemaType(type="Bool") for name in boolean_fields}
    attributes.update({name: SchemaType(type="String") for name in string_fields})
    return SchemaType(type="Record", attributes=attributes, required=False)


def medical_context_schema() -> SchemaType:
    schema = _record(
        {
            "is_write",
            "payload_present",
            "patient_id_present",
            "subject_reference_present",
            "subject_is_patient",
            "purpose_present",
            "purpose_is_patient_care",
            "query_has_identifier",
            "query_is_broad",
            "count_present",
            "count_is_narrow",
            "resource_id_present",
            "medication_concept_present",
            "dosage_present",
            "authored_on_present",
            "issued_present",
            "observation_category_present",
            "observation_category_system_present",
            "observation_category_display_present",
            "service_request_code_present",
        },
        {
            "canonical_tool",
            "current_patient_id",
            "resource_type",
            "status",
            "intent",
            "priority",
        },
    )
    schema.attributes["count"] = SchemaType(type="Long")
    return schema


def session_context_schema() -> SchemaType:
    schema = _record(
        {
            "last_tool_error",
            "last_get_patient_returned_multiple",
            "user_specified_urgency",
            "user_specified_backdate",
            "user_specified_correction",
            "user_confirmed_allergy_check",
            "last_assistant_restated_patient",
            "user_confirmed_write",
            "pending_write_confirmed",
            "current_call_is_duplicate",
            "current_call_retries_failed_write",
            "current_call_patient_mismatch",
            "current_call_is_backdated",
            "current_call_is_correction",
            "current_call_patient_unseen",
        },
        {"now_timestamp", "now_date", "established_patient_id"},
    )
    for name in (
        "prior_post_signatures",
        "failed_post_signatures",
        "seen_patient_ids",
    ):
        schema.attributes[name] = SchemaType(
            type="Set", element=SchemaType(type="String")
        )
    return schema


class MedAgentBenchSchemaGenerator:
    """Generate a portable schema with generic and medical context facts."""

    def generate(self, spec: AgentSpec) -> GeneratedSchema:
        session = session_context_schema()
        model = agent_to_cedar_schema(
            spec.to_agent(),
            pre_tool_context_extensions={
                "normalized": normalized_context_schema(),
                "medical": medical_context_schema(),
                "session": session,
            },
            tool_output_context_extensions={"session": session_context_schema()},
        )
        native = Schema.from_json(model.model_dump_json(exclude_none=True))
        return GeneratedSchema(model=model, text=native.to_cedarschema())
