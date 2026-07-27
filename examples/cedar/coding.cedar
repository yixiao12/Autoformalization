@id("allow-prompts")
permit(principal, action == coding_agent::Action::"Prompt", resource);

@id("allow-tool-use")
permit(principal, action == coding_agent::Action::"PreToolUse", resource);

@id("allow-tool-output")
permit(principal, action == coding_agent::Action::"ToolOutput", resource);

@id("forbid-sensitive-write")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Write" &&
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*.git/*" ||
   context.parameters.file_path like "*credentials*" ||
   context.parameters.file_path like "*secrets*")
};

@id("forbid-sensitive-edit")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Edit" &&
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*id_rsa*" ||
   context.parameters.file_path like "*.pem*")
};

@id("forbid-dangerous-bash")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  (context.parameters.command like "*rm -rf /*" ||
   context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=/dev/zero*" ||
   context.parameters.command like "*> /dev/sda*")
};

@id("forbid-untrusted-fetch")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "WebFetch" &&
  context has parameters &&
  (context.parameters.url like "*pastebin*" ||
   context.parameters.url like "*raw.githubusercontent.com*")
};

@id("rate-limit-trajectory")
forbid(
  principal,
  action,
  resource
)
when {
  resource has step_count &&
  resource.step_count > 1000
};