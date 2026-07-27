@id("default-permit-prompt")
@source("infrastructure")
permit(
  principal,
  action == coding_agent::Action::"Prompt",
  resource
);

@id("default-permit-pretooluse")
@source("infrastructure")
permit(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
);

@id("default-permit-tooloutput")
@source("infrastructure")
permit(
  principal,
  action == coding_agent::Action::"ToolOutput",
  resource
);

@id("forbid-cag-001-sensitive-writes")
@source("policy.md#CAG-001")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Write" &&
  context has parameters &&
  context.parameters has file_path &&
  (
    context.parameters.file_path like "*.env*" ||
    context.parameters.file_path like "*credentials*" ||
    context.parameters.file_path like "*secrets*"
  )
};

@id("forbid-cag-002-sensitive-edits")
@source("policy.md#CAG-002")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Edit" &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.path_present &&
  (
    context.normalized.path_is_env_file ||
    context.normalized.path_basename == "id_rsa" ||
    context.normalized.path_is_pem_file
  )
};

@id("forbid-cag-003-git-metadata-integrity")
@source("policy.md#CAG-003")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  (resource.name == "Write" || resource.name == "Edit") &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.path_present &&
  context.normalized.path_segments.contains(".git")
};

@id("forbid-cag-004-sensitive-reads")
@source("policy.md#CAG-004")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Read" &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.path_present &&
  (
    context.normalized.path_is_env_file ||
    context.normalized.path_is_private_key ||
    context.normalized.path_is_pem_file ||
    context.normalized.path_is_aws_credentials
  )
};

@id("forbid-cag-005-secret-oriented-search")
@source("policy.md#CAG-005")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Grep" &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.search_present &&
  (
    context.normalized.search_targets_private_key ||
    context.normalized.search_targets_secret_assignment
  )
};

@id("forbid-cag-006-sensitive-directory-discovery")
@source("policy.md#CAG-006")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Glob" &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.glob_enumerates_sensitive_directory
};

@id("forbid-cag-007-private-key-creation")
@source("policy.md#CAG-007")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Write" &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.content_present &&
  context.normalized.content_has_private_key_header
};

@id("forbid-cag-008-secret-insertion")
@source("policy.md#CAG-008")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Edit" &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.content_present &&
  (
    context.normalized.content_has_private_key_header ||
    context.normalized.content_has_secret_assignment
  )
};

@id("forbid-cag-009-destructive-deletion")
@source("policy.md#CAG-009")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Bash" &&
  context has normalized &&
  context.normalized.shell_parse_ok &&
  context.normalized.command_present &&
  context.normalized.shell_deletes_root_or_home
};

@id("forbid-cag-010-disk-destruction")
@source("policy.md#CAG-010")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Bash" &&
  context has normalized &&
  context.normalized.shell_parse_ok &&
  context.normalized.command_present &&
  (
    context.normalized.shell_formats_device ||
    context.normalized.shell_writes_block_device
  )
};

@id("forbid-cag-011-raw-device-redirection")
@source("policy.md#CAG-011")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Bash" &&
  context has normalized &&
  context.normalized.shell_parse_ok &&
  context.normalized.command_present &&
  context.normalized.shell_writes_block_device
};

@id("forbid-cag-012-host-shutdown")
@source("policy.md#CAG-012")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Bash" &&
  context has normalized &&
  context.normalized.shell_parse_ok &&
  context.normalized.command_present &&
  context.normalized.shell_invokes_shutdown
};

@id("forbid-cag-013-privilege-escalation")
@source("policy.md#CAG-013")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Bash" &&
  context has normalized &&
  context.normalized.shell_parse_ok &&
  context.normalized.command_present &&
  context.normalized.shell_uses_privilege_escalation
};

@id("forbid-cag-014-remote-script-execution")
@source("policy.md#CAG-014")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Bash" &&
  context has normalized &&
  context.normalized.shell_parse_ok &&
  context.normalized.command_present &&
  context.normalized.shell_downloads_to_shell
};

@id("forbid-cag-015-command-timeout")
@source("policy.md#CAG-015")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "Bash" &&
  context has parameters &&
  context.parameters has timeout &&
  context.parameters.timeout > 300000
};

@id("forbid-cag-016-secure-web-transport")
@source("policy.md#CAG-016")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "WebFetch" &&
  context has normalized &&
  context.normalized.url_parse_ok &&
  context.normalized.url_present &&
  !context.normalized.url_is_https
};

@id("forbid-cag-017-untrusted-fetch-sources")
@source("policy.md#CAG-017")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "WebFetch" &&
  context has normalized &&
  context.normalized.url_parse_ok &&
  context.normalized.url_present &&
  (
    context.normalized.url_host_suffixes.contains("pastebin.com") ||
    context.normalized.url_host_suffixes.contains("raw.githubusercontent.com") ||
    context.normalized.url_host_suffixes.contains("gist.github.com") ||
    context.normalized.url_host_suffixes.contains("gist.githubusercontent.com")
  )
};

@id("forbid-cag-018-credential-hunting-searches")
@source("policy.md#CAG-018")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  resource.name == "WebSearch" &&
  context has normalized &&
  context.normalized.parse_ok &&
  context.normalized.search_present &&
  context.normalized.search_is_credential_hunting
};

@id("forbid-cag-019-private-key-output")
@source("policy.md#CAG-019")
forbid(
  principal,
  action == coding_agent::Action::"ToolOutput",
  resource
)
when {
  context.content like "*-----BEGIN *PRIVATE KEY-----*"
};

@id("forbid-cag-020-cloud-secret-output")
@source("policy.md#CAG-020")
forbid(
  principal,
  action == coding_agent::Action::"ToolOutput",
  resource
)
when {
  context.content like "*AWS_SECRET_ACCESS_KEY*" ||
  context.content like "*SECRET_TOKEN=*"
};