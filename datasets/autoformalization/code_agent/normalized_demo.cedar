// Demonstrates policies over deterministic context.normalized fields.
@id("default-prompt")
@source("infrastructure")
permit(principal, action == coding_agent::Action::"Prompt", resource);

@id("default-tools")
@source("infrastructure")
permit(principal, action == coding_agent::Action::"PreToolUse", resource);

@id("default-output")
@source("infrastructure")
permit(principal, action == coding_agent::Action::"ToolOutput", resource);

@id("normalized-shutdown")
@source("policy.md#CAG-012")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context has normalized &&
  context.normalized.shell_invokes_shutdown
};

@id("normalized-download-shell")
@source("policy.md#CAG-014")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context has normalized &&
  context.normalized.shell_downloads_to_shell
};

@id("normalized-untrusted-host")
@source("policy.md#CAG-017")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context has normalized &&
  context.normalized.url_host_suffixes.contains("pastebin.com")
};

@id("normalized-secret-search")
@source("policy.md#CAG-005")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context has normalized &&
  context.normalized.search_targets_secret_assignment
};
