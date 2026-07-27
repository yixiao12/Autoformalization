// Infrastructure permits. These are not part of the 20-rule corpus.
@id("default-allow-prompts")
@source("infrastructure")
@description("Allow prompts unless a forbid policy applies")
permit(principal, action == coding_agent::Action::"Prompt", resource);

@id("default-allow-tool-use")
@source("infrastructure")
@description("Allow tool calls unless a forbid policy applies")
permit(principal, action == coding_agent::Action::"PreToolUse", resource);

@id("default-allow-tool-output")
@source("infrastructure")
@description("Allow tool output unless a forbid policy applies")
permit(principal, action == coding_agent::Action::"ToolOutput", resource);

@id("cag-001-sensitive-write")
@source("policy.md#CAG-001")
@description("Forbid Write on environment, credential, and secret paths")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Write" &&
  context has parameters && context.parameters has file_path &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*credentials*" ||
   context.parameters.file_path like "*secrets*")
};

@id("cag-002-sensitive-edit")
@source("policy.md#CAG-002")
@description("Forbid Edit on environment and private-key files")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Edit" &&
  context has parameters && context.parameters has file_path &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*id_rsa*" ||
   context.parameters.file_path like "*.pem*")
};

@id("cag-003-git-metadata-integrity")
@source("policy.md#CAG-003")
@description("Forbid Write and Edit under .git directories")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  (context.tool == "Write" || context.tool == "Edit") &&
  context has parameters && context.parameters has file_path &&
  context.parameters.file_path like "*.git/*"
};

@id("cag-004-sensitive-read")
@source("policy.md#CAG-004")
@description("Forbid Read on environment, SSH, PEM, and AWS credential files")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Read" &&
  context has parameters && context.parameters has file_path &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*.ssh/id_*" ||
   context.parameters.file_path like "*.pem*" ||
   context.parameters.file_path like "*.aws/credentials*")
};

@id("cag-005-secret-oriented-search")
@source("policy.md#CAG-005")
@description("Forbid Grep searches targeting common secret assignments")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Grep" &&
  context has parameters && context.parameters has pattern &&
  (context.parameters.pattern like "*BEGIN*PRIVATE KEY*" ||
   context.parameters.pattern like "*API_KEY=*" ||
   context.parameters.pattern like "*password=*")
};

@id("cag-006-sensitive-directory-discovery")
@source("policy.md#CAG-006")
@description("Forbid Glob enumeration of sensitive directories")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Glob" &&
  context has parameters && context.parameters has pattern &&
  (context.parameters.pattern like "*.ssh/*" ||
   context.parameters.pattern like "*.aws/*" ||
   context.parameters.pattern like "*.git/*")
};

@id("cag-007-private-key-creation")
@source("policy.md#CAG-007")
@description("Forbid writing private-key material")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Write" &&
  context has parameters && context.parameters has content &&
  context.parameters.content like "*-----BEGIN*PRIVATE KEY-----*"
};

@id("cag-008-secret-insertion")
@source("policy.md#CAG-008")
@description("Forbid inserting private keys and secret assignments")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Edit" &&
  context has parameters && context.parameters has new_string &&
  (context.parameters.new_string like "*-----BEGIN*PRIVATE KEY-----*" ||
   context.parameters.new_string like "*AWS_SECRET_ACCESS_KEY*" ||
   context.parameters.new_string like "*API_KEY=*")
};

@id("cag-009-destructive-deletion")
@source("policy.md#CAG-009")
@description("Forbid recursive force deletion of root or home")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Bash" &&
  context has parameters && context.parameters has command &&
  (context.parameters.command like "*rm -rf /" ||
   context.parameters.command like "*rm -rf /* --no-preserve-root*" ||
   context.parameters.command like "*rm -rf ~" ||
   context.parameters.command like "*rm -rf $HOME*")
};

@id("cag-010-disk-destruction")
@source("policy.md#CAG-010")
@description("Forbid filesystem formatting and disk overwrite commands")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Bash" &&
  context has parameters && context.parameters has command &&
  (context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=/dev/zero*")
};

@id("cag-011-raw-device-redirection")
@source("policy.md#CAG-011")
@description("Forbid redirecting output to raw disk devices")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Bash" &&
  context has parameters && context.parameters has command &&
  (context.parameters.command like "*> /dev/sd*" ||
   context.parameters.command like "*>/dev/sd*")
};

@id("cag-012-host-shutdown")
@source("policy.md#CAG-012")
@description("Forbid host shutdown and restart commands")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Bash" &&
  context has parameters && context.parameters has command &&
  (context.parameters.command like "*shutdown*" ||
   context.parameters.command like "*reboot*" ||
   context.parameters.command like "*poweroff*" ||
   context.parameters.command like "*halt*")
};

@id("cag-013-privilege-escalation")
@source("policy.md#CAG-013")
@description("Forbid sudo and root-shell escalation")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Bash" &&
  context has parameters && context.parameters has command &&
  (context.parameters.command like "sudo *" ||
   context.parameters.command like "* sudo *" ||
   context.parameters.command like "su -*" ||
   context.parameters.command like "* su -*")
};

@id("cag-014-remote-script-execution")
@source("policy.md#CAG-014")
@description("Forbid piping curl or wget downloads directly to a shell")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Bash" &&
  context has parameters && context.parameters has command &&
  ((context.parameters.command like "*curl*|*sh*" ||
    context.parameters.command like "*curl*|*bash*") ||
   (context.parameters.command like "*wget*|*sh*" ||
    context.parameters.command like "*wget*|*bash*"))
};

@id("cag-015-command-timeout")
@source("policy.md#CAG-015")
@description("Forbid Bash timeouts above 300000 milliseconds")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "Bash" &&
  context has parameters && context.parameters has timeout &&
  context.parameters.timeout > 300000
};

@id("cag-016-secure-web-transport")
@source("policy.md#CAG-016")
@description("Forbid non-HTTPS WebFetch URLs")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "WebFetch" &&
  context has parameters && context.parameters has url &&
  !(context.parameters.url like "https://*")
};

@id("cag-017-untrusted-fetch-sources")
@source("policy.md#CAG-017")
@description("Forbid WebFetch from untrusted content-sharing sources")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "WebFetch" &&
  context has parameters && context.parameters has url &&
  (context.parameters.url like "*pastebin.com*" ||
   context.parameters.url like "*raw.githubusercontent.com*" ||
   context.parameters.url like "*gist.github.com*")
};

@id("cag-018-credential-hunting-searches")
@source("policy.md#CAG-018")
@description("Forbid web searches targeting leaked credentials")
forbid(principal, action == coding_agent::Action::"PreToolUse", resource)
when {
  context.tool == "WebSearch" &&
  context has parameters && context.parameters has query &&
  (context.parameters.query like "*password dump*" ||
   context.parameters.query like "*leaked credentials*" ||
   context.parameters.query like "*exposed API keys*")
};

@id("cag-019-private-key-output")
@source("policy.md#CAG-019")
@description("Deny tool output containing private-key material")
forbid(principal, action == coding_agent::Action::"ToolOutput", resource)
when {
  context.content like "*-----BEGIN*PRIVATE KEY-----*"
};

@id("cag-020-cloud-secret-output")
@source("policy.md#CAG-020")
@description("Deny tool output containing cloud secret assignments")
forbid(principal, action == coding_agent::Action::"ToolOutput", resource)
when {
  context.content like "*AWS_SECRET_ACCESS_KEY*" ||
  context.content like "*SECRET_TOKEN=*"
};
