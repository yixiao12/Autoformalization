"""Deterministic security-oriented normalization for tool-call arguments."""

from __future__ import annotations

import json
import posixpath
import re
import shlex
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from cedar.schema import SchemaType

from sondera import ToolCall  # type: ignore[attr-defined]

NORMALIZED_CONTEXT_GUIDE = """The optional `context.normalized` record is produced
by trusted deterministic code before Cedar evaluation. Prefer its exact booleans,
sets, and normalized components over `like` matching on raw strings. In particular:
- path_* fields distinguish exact filenames/components from incidental substrings;
- shell_* fields come from shell tokenization and command/pipeline structure;
- url_* fields use lowercase IDNA hosts and exact domain suffix components;
- search_* and content_* fields identify assignment/header intent.
Guard access with `context has normalized`. If a critical decision requires parsing,
also require the corresponding *_parse_ok field. Raw fields remain available only
for requirements not represented by normalized fields.
"""

_PRIVATE_KEY_NAMES = {
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_ecdsa_sk",
    "id_ed25519_sk",
    "identity",
}
_SENSITIVE_DIRECTORIES = {".ssh", ".aws", ".git"}
_SHUTDOWN_COMMANDS = {"shutdown", "reboot", "poweroff", "halt"}
_SHELL_INTERPRETERS = {
    "sh",
    "bash",
    "dash",
    "zsh",
    "ksh",
    "fish",
    "powershell",
    "pwsh",
}
_DOWNLOADERS = {"curl", "wget"}
_BLOCK_DEVICE = re.compile(r"^/dev/(?:sd|hd|vd|xvd|nvme|mmcblk)[a-z0-9]*$")
_PRIVATE_KEY_HEADER = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----", re.IGNORECASE
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9_])(?:API_KEY|AWS_SECRET_ACCESS_KEY|SECRET_TOKEN)\s*=",
    re.IGNORECASE,
)


def normalized_context_schema() -> SchemaType:
    """Return the Cedar type for the trusted normalized context extension."""
    boolean_fields = {
        "parse_ok",
        "path_present",
        "path_contains_env",
        "path_is_env_file",
        "path_has_credentials_component",
        "path_has_secrets_component",
        "path_is_private_key",
        "path_is_pem_file",
        "path_is_aws_credentials",
        "path_is_sensitive_directory",
        "glob_enumerates_sensitive_directory",
        "command_present",
        "shell_parse_ok",
        "shell_deletes_root_or_home",
        "shell_formats_device",
        "shell_writes_block_device",
        "shell_invokes_shutdown",
        "shell_uses_privilege_escalation",
        "shell_downloads_to_shell",
        "url_present",
        "url_parse_ok",
        "url_is_https",
        "search_present",
        "search_targets_private_key",
        "search_targets_secret_assignment",
        "search_is_credential_hunting",
        "content_present",
        "content_has_private_key_header",
        "content_has_secret_assignment",
    }
    string_fields = {
        "path_normalized",
        "path_basename",
        "path_suffix",
        "url_scheme",
        "url_host",
        "search_normalized",
    }
    attributes = {name: SchemaType(type="Bool") for name in boolean_fields}
    attributes.update({name: SchemaType(type="String") for name in string_fields})
    attributes.update(
        {
            "path_segments": SchemaType(type="Set", element=SchemaType(type="String")),
            "shell_executables": SchemaType(
                type="Set", element=SchemaType(type="String")
            ),
            "url_host_suffixes": SchemaType(
                type="Set", element=SchemaType(type="String")
            ),
        }
    )
    return SchemaType(type="Record", attributes=attributes, required=False)


def _empty_facts() -> dict[str, object]:
    return {
        "parse_ok": False,
        "path_present": False,
        "path_normalized": "",
        "path_basename": "",
        "path_suffix": "",
        "path_segments": [],
        "path_contains_env": False,
        "path_is_env_file": False,
        "path_has_credentials_component": False,
        "path_has_secrets_component": False,
        "path_is_private_key": False,
        "path_is_pem_file": False,
        "path_is_aws_credentials": False,
        "path_is_sensitive_directory": False,
        "glob_enumerates_sensitive_directory": False,
        "command_present": False,
        "shell_parse_ok": False,
        "shell_executables": [],
        "shell_deletes_root_or_home": False,
        "shell_formats_device": False,
        "shell_writes_block_device": False,
        "shell_invokes_shutdown": False,
        "shell_uses_privilege_escalation": False,
        "shell_downloads_to_shell": False,
        "url_present": False,
        "url_parse_ok": False,
        "url_scheme": "",
        "url_host": "",
        "url_host_suffixes": [],
        "url_is_https": False,
        "search_present": False,
        "search_normalized": "",
        "search_targets_private_key": False,
        "search_targets_secret_assignment": False,
        "search_is_credential_hunting": False,
        "content_present": False,
        "content_has_private_key_header": False,
        "content_has_secret_assignment": False,
    }


def _normalized_path(value: str) -> tuple[str, list[str]]:
    replaced = value.replace("\\", "/")
    normalized = posixpath.normpath(replaced).lower()
    segments = [part for part in PurePosixPath(normalized).parts if part != "/"]
    return normalized, segments


def _path_facts(tool: str, arguments: dict[str, Any]) -> dict[str, object]:
    raw_path = arguments.get("file_path")
    if not isinstance(raw_path, str):
        raw_path = arguments.get("path")
    if not isinstance(raw_path, str):
        raw_path = ""
    normalized, segments = _normalized_path(raw_path) if raw_path else ("", [])
    basename = segments[-1] if segments else ""
    suffix = PurePosixPath(basename).suffix.lower() if basename else ""
    facts: dict[str, object] = {
        "path_present": bool(raw_path),
        "path_normalized": normalized,
        "path_basename": basename,
        "path_suffix": suffix,
        "path_segments": sorted(set(segments)),
        "path_contains_env": ".env" in normalized,
        "path_is_env_file": basename == ".env" or basename.startswith(".env."),
        "path_has_credentials_component": "credentials" in segments,
        "path_has_secrets_component": "secrets" in segments,
        "path_is_private_key": basename in _PRIVATE_KEY_NAMES,
        "path_is_pem_file": suffix == ".pem",
        "path_is_aws_credentials": (
            len(segments) >= 2
            and segments[-2] == ".aws"
            and segments[-1] == "credentials"
        ),
        "path_is_sensitive_directory": bool(set(segments) & _SENSITIVE_DIRECTORIES),
    }
    pattern = arguments.get("pattern")
    combined = f"{raw_path}/{pattern}" if isinstance(pattern, str) else raw_path
    pattern_segments = {
        item
        for item in re.split(r"[/\\]+", combined.lower())
        if item and item not in {"*", "**"}
    }
    facts["glob_enumerates_sensitive_directory"] = tool == "Glob" and bool(
        pattern_segments & _SENSITIVE_DIRECTORIES
    )
    return facts


def _shell_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _executable(segment: list[str]) -> tuple[str, list[str]]:
    words = [item for item in segment if not set(item) <= set("|;&<>")]
    while words and "=" in words[0] and not words[0].startswith(("/", "./")):
        name = words[0].split("=", 1)[0]
        if not name.replace("_", "a").isalnum():
            break
        words.pop(0)
    if not words:
        return "", []
    executable = PurePosixPath(words[0]).name.lower()
    return executable, words[1:]


def _wrapped_command(executable: str, arguments: list[str]) -> tuple[str, list[str]]:
    if executable not in {"sudo", "env", "command", "nohup"}:
        return "", []
    index = 0
    options_with_values = {
        "-u",
        "--user",
        "-g",
        "--group",
        "-h",
        "--host",
        "-p",
        "--prompt",
        "-c",
        "--close-from",
    }
    while index < len(arguments):
        item = arguments[index]
        if item == "--":
            index += 1
            break
        if executable == "env" and "=" in item and not item.startswith("-"):
            index += 1
            continue
        if item in options_with_values:
            index += 2
            continue
        if item.startswith("-"):
            index += 1
            continue
        break
    if index >= len(arguments):
        return "", []
    return PurePosixPath(arguments[index]).name.lower(), arguments[index + 1 :]


def _segment_commands(
    segment: list[str], *, depth: int = 0
) -> list[tuple[str, list[str]]]:
    executable, arguments = _executable(segment)
    if not executable:
        return []
    commands = [(executable, arguments)]
    wrapped = _wrapped_command(executable, arguments)
    if wrapped[0]:
        commands.append(wrapped)
    if depth >= 2:
        return commands
    for nested_shell, shell_arguments in list(commands):
        if nested_shell not in _SHELL_INTERPRETERS:
            continue
        command_index = next(
            (
                index
                for index, item in enumerate(shell_arguments)
                if item.startswith("-") and "c" in item[1:]
            ),
            None,
        )
        if command_index is None or command_index + 1 >= len(shell_arguments):
            continue
        try:
            nested_tokens = _shell_tokens(shell_arguments[command_index + 1])
        except ValueError:
            continue
        for group in _command_groups(nested_tokens):
            for nested_segment in group:
                commands.extend(_segment_commands(nested_segment, depth=depth + 1))
    return commands


def _command_groups(tokens: list[str]) -> list[list[list[str]]]:
    groups: list[list[list[str]]] = []
    pipeline: list[list[str]] = []
    segment: list[str] = []
    for symbol in tokens:
        if symbol == "|":
            pipeline.append(segment)
            segment = []
        elif symbol in {";", "&&", "||", "&"}:
            pipeline.append(segment)
            groups.append(pipeline)
            pipeline = []
            segment = []
        else:
            segment.append(symbol)
    pipeline.append(segment)
    groups.append(pipeline)
    return [group for group in groups if any(group)]


def _rm_targets_root_or_home(arguments: list[str]) -> bool:
    recursive = False
    force = False
    targets: list[str] = []
    options_done = False
    for item in arguments:
        if item == "--":
            options_done = True
            continue
        if not options_done and item.startswith("--"):
            recursive |= item == "--recursive"
            force |= item == "--force"
            continue
        if not options_done and item.startswith("-"):
            flags = item[1:].lower()
            recursive |= "r" in flags
            force |= "f" in flags
            continue
        targets.append(item.rstrip("/") or "/")
    dangerous_targets = {"/", "~", "$HOME", "${HOME}"}
    return recursive and force and any(item in dangerous_targets for item in targets)


def _is_block_device(value: str) -> bool:
    return bool(_BLOCK_DEVICE.fullmatch(value.rstrip(";,")))


def _command_facts(command: str) -> dict[str, object]:
    facts: dict[str, object] = {
        "command_present": True,
        "shell_parse_ok": False,
        "shell_executables": [],
        "shell_deletes_root_or_home": False,
        "shell_formats_device": False,
        "shell_writes_block_device": False,
        "shell_invokes_shutdown": False,
        "shell_uses_privilege_escalation": False,
        "shell_downloads_to_shell": False,
    }
    try:
        tokens = _shell_tokens(command)
    except ValueError:
        return facts

    groups = _command_groups(tokens)
    parsed = [
        [_segment_commands(segment) for segment in pipeline if segment]
        for pipeline in groups
    ]
    executables = {
        executable
        for pipeline in parsed
        for stage in pipeline
        for executable, _ in stage
    }
    facts["shell_parse_ok"] = True
    facts["shell_executables"] = sorted(executables)
    facts["shell_invokes_shutdown"] = bool(executables & _SHUTDOWN_COMMANDS)
    facts["shell_uses_privilege_escalation"] = "sudo" in executables or any(
        executable == "su" and "-" in arguments
        for pipeline in parsed
        for stage in pipeline
        for executable, arguments in stage
    )
    facts["shell_deletes_root_or_home"] = any(
        executable == "rm" and _rm_targets_root_or_home(arguments)
        for pipeline in parsed
        for stage in pipeline
        for executable, arguments in stage
    )
    facts["shell_formats_device"] = any(
        executable.startswith("mkfs") or executable in {"mke2fs", "newfs"}
        for pipeline in parsed
        for stage in pipeline
        for executable, _ in stage
    )
    dd_zero_to_device = any(
        executable == "dd"
        and any(item == "if=/dev/zero" for item in arguments)
        and any(
            item.startswith("of=") and _is_block_device(item.split("=", 1)[1])
            for item in arguments
        )
        for pipeline in parsed
        for stage in pipeline
        for executable, arguments in stage
    )
    facts["shell_formats_device"] = bool(
        facts["shell_formats_device"] or dd_zero_to_device
    )
    facts["shell_writes_block_device"] = dd_zero_to_device or any(
        set(token) <= set("><|")
        and ">" in token
        and index + 1 < len(tokens)
        and _is_block_device(tokens[index + 1])
        for index, token in enumerate(tokens)
    )
    facts["shell_downloads_to_shell"] = any(
        any(executable in _DOWNLOADERS for stage in pipeline for executable, _ in stage)
        and any(
            executable in _SHELL_INTERPRETERS
            for stage in pipeline[1:]
            for executable, _ in stage
        )
        for pipeline in parsed
        if len(pipeline) > 1
    )
    return facts


def _url_facts(url: str) -> dict[str, object]:
    facts: dict[str, object] = {
        "url_present": True,
        "url_parse_ok": False,
        "url_scheme": "",
        "url_host": "",
        "url_host_suffixes": [],
        "url_is_https": False,
    }
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        return facts
    if not parsed.scheme or not host:
        return facts
    labels = host.split(".")
    suffixes = [".".join(labels[index:]) for index in range(len(labels))]
    facts.update(
        {
            "url_parse_ok": True,
            "url_scheme": parsed.scheme.lower(),
            "url_host": host,
            "url_host_suffixes": suffixes,
            "url_is_https": parsed.scheme.lower() == "https",
        }
    )
    return facts


def _search_facts(tool: str, arguments: dict[str, Any]) -> dict[str, object]:
    value = arguments.get("pattern" if tool == "Grep" else "query")
    if not isinstance(value, str):
        return {}
    normalized = " ".join(value.lower().split())
    private_key = all(word in normalized for word in ("begin", "private", "key"))
    assignment_name = re.search(
        r"(?<![a-z0-9_])(?:api_key|password|aws_secret_access_key)", normalized
    )
    secret_assignment = bool(assignment_name and "=" in normalized)
    credential_terms = {"credential", "credentials", "password", "passwords"}
    exposure_terms = {"dump", "dumps", "leaked", "exposed"}
    words = set(re.findall(r"[a-z_]+", normalized))
    credential_hunting = bool(
        (words & credential_terms and words & exposure_terms)
        or ({"api", "keys"} <= words and words & {"leaked", "exposed"})
    )
    return {
        "search_present": True,
        "search_normalized": normalized,
        "search_targets_private_key": private_key,
        "search_targets_secret_assignment": secret_assignment,
        "search_is_credential_hunting": credential_hunting,
    }


def _content_facts(tool: str, arguments: dict[str, Any]) -> dict[str, object]:
    field = "new_string" if tool == "Edit" else "content"
    value = arguments.get(field)
    if not isinstance(value, str):
        return {}
    return {
        "content_present": True,
        "content_has_private_key_header": bool(_PRIVATE_KEY_HEADER.search(value)),
        "content_has_secret_assignment": bool(_SECRET_ASSIGNMENT.search(value)),
    }


class SecurityContextNormalizer:
    """Create trusted, policy-neutral security facts from a ToolCall."""

    def normalize(self, tool: str, arguments: Any) -> dict[str, object]:
        facts = _empty_facts()
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return facts
        if not isinstance(arguments, dict):
            return facts
        facts["parse_ok"] = True
        facts.update(_path_facts(tool, arguments))
        command = arguments.get("command")
        if tool == "Bash" and isinstance(command, str):
            facts.update(_command_facts(command))
        url = arguments.get("url")
        if tool == "WebFetch" and isinstance(url, str):
            facts.update(_url_facts(url))
        if tool in {"Grep", "WebSearch"}:
            facts.update(_search_facts(tool, arguments))
        if tool in {"Write", "Edit"}:
            facts.update(_content_facts(tool, arguments))
        return facts

    def enrich(self, tool_call: ToolCall) -> dict[str, object]:
        """Return the context extension consumed by CedarPolicyHarness."""
        return {"normalized": self.normalize(tool_call.tool, tool_call.arguments)}
