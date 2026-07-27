@id("default-prompt")
@source("default#Prompt")
permit(
  principal,
  action == coding_agent::Action::"Prompt",
  resource
);

@id("default-pretooluse")
@source("default#PreToolUse")
permit(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
);

@id("default-tooloutput")
@source("default#ToolOutput")
permit(
  principal,
  action == coding_agent::Action::"ToolOutput",
  resource
);

@id("cag-001-sensitive-writes")
@source("policy.md#CAG-001")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Write" &&
  context has parameters &&
  context.parameters has file_path &&
  (
    context.parameters.file_path like "*.env*" ||
    context.parameters.file_path like "*credentials*" ||
    context.parameters.file_path like "*secrets*"
  )
};

@id("cag-002-sensitive-edits")
@source("policy.md#CAG-002")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Edit" &&
  context has parameters &&
  context.parameters has file_path &&
  (
    context.parameters.file_path like ".env" ||
    context.parameters.file_path like "*/.env" ||
    context.parameters.file_path like ".env.*" ||
    context.parameters.file_path like "*/.env.*" ||
    context.parameters.file_path like "id_rsa" ||
    context.parameters.file_path like "*/id_rsa" ||
    context.parameters.file_path like "*.pem"
  )
};

@id("cag-003-git-metadata-integrity")
@source("policy.md#CAG-003")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  (context.tool == "Write" || context.tool == "Edit") &&
  context has parameters &&
  context.parameters has file_path &&
  (
    context.parameters.file_path like ".git/*" ||
    context.parameters.file_path like "*/.git/*"
  )
};

@id("cag-004-sensitive-reads")
@source("policy.md#CAG-004")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Read" &&
  context has parameters &&
  context.parameters has file_path &&
  (
    context.parameters.file_path like ".env" ||
    context.parameters.file_path like "*/.env" ||
    context.parameters.file_path like ".env.*" ||
    context.parameters.file_path like "*/.env.*" ||
    context.parameters.file_path like "id_rsa" ||
    context.parameters.file_path like "*/id_rsa" ||
    context.parameters.file_path like "id_ed25519" ||
    context.parameters.file_path like "*/id_ed25519" ||
    context.parameters.file_path like "id_ecdsa" ||
    context.parameters.file_path like "*/id_ecdsa" ||
    context.parameters.file_path like "id_dsa" ||
    context.parameters.file_path like "*/id_dsa" ||
    context.parameters.file_path like "id_ed25519_sk" ||
    context.parameters.file_path like "*/id_ed25519_sk" ||
    context.parameters.file_path like "id_ecdsa_sk" ||
    context.parameters.file_path like "*/id_ecdsa_sk" ||
    context.parameters.file_path like "*.pem" ||
    context.parameters.file_path like ".aws/credentials" ||
    context.parameters.file_path like "*/.aws/credentials"
  )
};

@id("cag-005-secret-oriented-search")
@source("policy.md#CAG-005")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Grep" &&
  context has parameters &&
  context.parameters has pattern &&
  (
    context.parameters.pattern like "*-----BEGIN *PRIVATE KEY-----*" ||
    context.parameters.pattern like "*API_KEY=*" ||
    context.parameters.pattern like "*API_KEY =*" ||
    context.parameters.pattern like "*API_KEY\\s*=*" ||
    context.parameters.pattern like "*API_KEY[[:space:]]*=*" ||
    context.parameters.pattern like "*password=*" ||
    context.parameters.pattern like "*password =*" ||
    context.parameters.pattern like "*password\\s*=*" ||
    context.parameters.pattern like "*password[[:space:]]*=*"
  )
};

@id("cag-006-sensitive-directory-discovery-pattern")
@source("policy.md#CAG-006")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Glob" &&
  context has parameters &&
  context.parameters has pattern &&
  (
    context.parameters.pattern like ".ssh/*" ||
    context.parameters.pattern like "*/.ssh/*" ||
    context.parameters.pattern like ".aws/*" ||
    context.parameters.pattern like "*/.aws/*" ||
    context.parameters.pattern like ".git/*" ||
    context.parameters.pattern like "*/.git/*"
  )
};

@id("cag-006-sensitive-directory-discovery-path")
@source("policy.md#CAG-006")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Glob" &&
  context has parameters &&
  context.parameters has path &&
  (
    context.parameters.path like ".ssh" ||
    context.parameters.path like ".ssh/*" ||
    context.parameters.path like "*/.ssh" ||
    context.parameters.path like "*/.ssh/*" ||
    context.parameters.path like ".aws" ||
    context.parameters.path like ".aws/*" ||
    context.parameters.path like "*/.aws" ||
    context.parameters.path like "*/.aws/*" ||
    context.parameters.path like ".git" ||
    context.parameters.path like ".git/*" ||
    context.parameters.path like "*/.git" ||
    context.parameters.path like "*/.git/*"
  )
};

@id("cag-007-private-key-creation")
@source("policy.md#CAG-007")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Write" &&
  context has parameters &&
  context.parameters has content &&
  context.parameters.content like "*-----BEGIN *PRIVATE KEY-----*"
};

@id("cag-008-secret-insertion")
@source("policy.md#CAG-008")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Edit" &&
  context has parameters &&
  context.parameters has new_string &&
  (
    context.parameters.new_string like "*-----BEGIN *PRIVATE KEY-----*" ||
    context.parameters.new_string like "*AWS_SECRET_ACCESS_KEY*" ||
    context.parameters.new_string like "*API_KEY=*" ||
    context.parameters.new_string like "*API_KEY =*"
  )
};

@id("cag-009-destructive-deletion-root")
@source("policy.md#CAG-009")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "*rm -rf /" ||
    context.parameters.command like "*rm -rf / *" ||
    context.parameters.command like "*rm -rf -- /" ||
    context.parameters.command like "*rm -rf -- / *" ||
    context.parameters.command like "*rm -fr /" ||
    context.parameters.command like "*rm -fr / *" ||
    context.parameters.command like "*rm -fr -- /" ||
    context.parameters.command like "*rm -fr -- / *" ||
    context.parameters.command like "*rm -Rf /" ||
    context.parameters.command like "*rm -Rf / *" ||
    context.parameters.command like "*rm -Rf -- /" ||
    context.parameters.command like "*rm -Rf -- / *" ||
    context.parameters.command like "*rm -r -f /" ||
    context.parameters.command like "*rm -r -f / *" ||
    context.parameters.command like "*rm -r -f -- /" ||
    context.parameters.command like "*rm -r -f -- / *" ||
    context.parameters.command like "*rm -f -r /" ||
    context.parameters.command like "*rm -f -r / *" ||
    context.parameters.command like "*rm -f -r -- /" ||
    context.parameters.command like "*rm -f -r -- / *"
  )
};

@id("cag-009-destructive-deletion-home")
@source("policy.md#CAG-009")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "*rm -rf ~" ||
    context.parameters.command like "*rm -rf ~ *" ||
    context.parameters.command like "*rm -rf -- ~" ||
    context.parameters.command like "*rm -rf -- ~ *" ||
    context.parameters.command like "*rm -fr ~" ||
    context.parameters.command like "*rm -fr ~ *" ||
    context.parameters.command like "*rm -fr -- ~" ||
    context.parameters.command like "*rm -fr -- ~ *" ||
    context.parameters.command like "*rm -Rf ~" ||
    context.parameters.command like "*rm -Rf ~ *" ||
    context.parameters.command like "*rm -Rf -- ~" ||
    context.parameters.command like "*rm -Rf -- ~ *" ||
    context.parameters.command like "*rm -r -f ~" ||
    context.parameters.command like "*rm -r -f ~ *" ||
    context.parameters.command like "*rm -r -f -- ~" ||
    context.parameters.command like "*rm -r -f -- ~ *" ||
    context.parameters.command like "*rm -f -r ~" ||
    context.parameters.command like "*rm -f -r ~ *" ||
    context.parameters.command like "*rm -f -r -- ~" ||
    context.parameters.command like "*rm -f -r -- ~ *" ||
    context.parameters.command like "*rm -rf $HOME" ||
    context.parameters.command like "*rm -rf $HOME *" ||
    context.parameters.command like "*rm -rf -- $HOME" ||
    context.parameters.command like "*rm -rf -- $HOME *" ||
    context.parameters.command like "*rm -fr $HOME" ||
    context.parameters.command like "*rm -fr $HOME *" ||
    context.parameters.command like "*rm -fr -- $HOME" ||
    context.parameters.command like "*rm -fr -- $HOME *" ||
    context.parameters.command like "*rm -Rf $HOME" ||
    context.parameters.command like "*rm -Rf $HOME *" ||
    context.parameters.command like "*rm -Rf -- $HOME" ||
    context.parameters.command like "*rm -Rf -- $HOME *" ||
    context.parameters.command like "*rm -r -f $HOME" ||
    context.parameters.command like "*rm -r -f $HOME *" ||
    context.parameters.command like "*rm -r -f -- $HOME" ||
    context.parameters.command like "*rm -r -f -- $HOME *" ||
    context.parameters.command like "*rm -f -r $HOME" ||
    context.parameters.command like "*rm -f -r $HOME *" ||
    context.parameters.command like "*rm -f -r -- $HOME" ||
    context.parameters.command like "*rm -f -r -- $HOME *"
  )
};

@id("cag-010-disk-destruction-format")
@source("policy.md#CAG-010")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "mkfs" ||
    context.parameters.command like "mkfs *" ||
    context.parameters.command like "mkfs.*" ||
    context.parameters.command like "mkfs.* *" ||
    context.parameters.command like "mke2fs" ||
    context.parameters.command like "mke2fs *" ||
    context.parameters.command like "* mkfs" ||
    context.parameters.command like "* mkfs *" ||
    context.parameters.command like "* mkfs.*" ||
    context.parameters.command like "* mkfs.* *" ||
    context.parameters.command like "* mke2fs" ||
    context.parameters.command like "* mke2fs *" ||
    context.parameters.command like "*;mkfs" ||
    context.parameters.command like "*;mkfs *" ||
    context.parameters.command like "*;mkfs.*" ||
    context.parameters.command like "*;mkfs.* *" ||
    context.parameters.command like "*;mke2fs" ||
    context.parameters.command like "*;mke2fs *" ||
    context.parameters.command like "*&&mkfs" ||
    context.parameters.command like "*&&mkfs *" ||
    context.parameters.command like "*&&mkfs.*" ||
    context.parameters.command like "*&&mkfs.* *" ||
    context.parameters.command like "*&&mke2fs" ||
    context.parameters.command like "*&&mke2fs *" ||
    context.parameters.command like "*||mkfs" ||
    context.parameters.command like "*||mkfs *" ||
    context.parameters.command like "*||mkfs.*" ||
    context.parameters.command like "*||mkfs.* *" ||
    context.parameters.command like "*||mke2fs" ||
    context.parameters.command like "*||mke2fs *"
  )
};

@id("cag-010-disk-destruction-zero")
@source("policy.md#CAG-010")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "*dd *if=/dev/zero*of=/dev/*" ||
    context.parameters.command like "*dd *of=/dev/*if=/dev/zero*"
  )
};

@id("cag-011-raw-device-redirection")
@source("policy.md#CAG-011")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "*>/dev/sd*" ||
    context.parameters.command like "*>>/dev/sd*" ||
    context.parameters.command like "*> /dev/sd*" ||
    context.parameters.command like "*>> /dev/sd*" ||
    context.parameters.command like "*>  /dev/sd*" ||
    context.parameters.command like "*>>  /dev/sd*" ||
    context.parameters.command like "*>   /dev/sd*" ||
    context.parameters.command like "*>>   /dev/sd*" ||
    context.parameters.command like "*>    /dev/sd*" ||
    context.parameters.command like "*>>    /dev/sd*"
  )
};

@id("cag-012-host-shutdown")
@source("policy.md#CAG-012")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "shutdown" ||
    context.parameters.command like "shutdown *" ||
    context.parameters.command like "reboot" ||
    context.parameters.command like "reboot *" ||
    context.parameters.command like "poweroff" ||
    context.parameters.command like "poweroff *" ||
    context.parameters.command like "halt" ||
    context.parameters.command like "halt *" ||
    context.parameters.command like "* shutdown" ||
    context.parameters.command like "* shutdown *" ||
    context.parameters.command like "* reboot" ||
    context.parameters.command like "* reboot *" ||
    context.parameters.command like "* poweroff" ||
    context.parameters.command like "* poweroff *" ||
    context.parameters.command like "* halt" ||
    context.parameters.command like "* halt *" ||
    context.parameters.command like "*;shutdown" ||
    context.parameters.command like "*;shutdown *" ||
    context.parameters.command like "*;reboot" ||
    context.parameters.command like "*;reboot *" ||
    context.parameters.command like "*;poweroff" ||
    context.parameters.command like "*;poweroff *" ||
    context.parameters.command like "*;halt" ||
    context.parameters.command like "*;halt *" ||
    context.parameters.command like "*&&shutdown" ||
    context.parameters.command like "*&&shutdown *" ||
    context.parameters.command like "*&&reboot" ||
    context.parameters.command like "*&&reboot *" ||
    context.parameters.command like "*&&poweroff" ||
    context.parameters.command like "*&&poweroff *" ||
    context.parameters.command like "*&&halt" ||
    context.parameters.command like "*&&halt *" ||
    context.parameters.command like "*||shutdown" ||
    context.parameters.command like "*||shutdown *" ||
    context.parameters.command like "*||reboot" ||
    context.parameters.command like "*||reboot *" ||
    context.parameters.command like "*||poweroff" ||
    context.parameters.command like "*||poweroff *" ||
    context.parameters.command like "*||halt" ||
    context.parameters.command like "*||halt *"
  )
};

@id("cag-013-privilege-escalation")
@source("policy.md#CAG-013")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "sudo" ||
    context.parameters.command like "sudo *" ||
    context.parameters.command like "su -" ||
    context.parameters.command like "su - *" ||
    context.parameters.command like "* sudo" ||
    context.parameters.command like "* sudo *" ||
    context.parameters.command like "* su -" ||
    context.parameters.command like "* su - *" ||
    context.parameters.command like "*;sudo" ||
    context.parameters.command like "*;sudo *" ||
    context.parameters.command like "*;su -" ||
    context.parameters.command like "*;su - *" ||
    context.parameters.command like "*&&sudo" ||
    context.parameters.command like "*&&sudo *" ||
    context.parameters.command like "*&&su -" ||
    context.parameters.command like "*&&su - *" ||
    context.parameters.command like "*||sudo" ||
    context.parameters.command like "*||sudo *" ||
    context.parameters.command like "*||su -" ||
    context.parameters.command like "*||su - *"
  )
};

@id("cag-014-remote-script-execution")
@source("policy.md#CAG-014")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has command &&
  (
    context.parameters.command like "*curl *|*sh" ||
    context.parameters.command like "*curl *|*sh *" ||
    context.parameters.command like "*curl *|*bash" ||
    context.parameters.command like "*curl *|*bash *" ||
    context.parameters.command like "*wget *|*sh" ||
    context.parameters.command like "*wget *|*sh *" ||
    context.parameters.command like "*wget *|*bash" ||
    context.parameters.command like "*wget *|*bash *"
  )
};

@id("cag-015-command-timeout")
@source("policy.md#CAG-015")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  context.parameters has timeout &&
  context.parameters.timeout > 300000
};

@id("cag-016-secure-web-transport")
@source("policy.md#CAG-016")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "WebFetch" &&
  context has parameters &&
  context.parameters has url &&
  !(context.parameters.url like "https://*")
};

@id("cag-017-untrusted-fetch-sources")
@source("policy.md#CAG-017")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "WebFetch" &&
  context has parameters &&
  context.parameters has url &&
  (
    context.parameters.url like "https://pastebin.com/*" ||
    context.parameters.url like "https://Pastebin.com/*" ||
    context.parameters.url like "https://*.pastebin.com/*" ||
    context.parameters.url like "https://*.Pastebin.com/*" ||
    context.parameters.url like "https://raw.githubusercontent.com/*" ||
    context.parameters.url like "https://*.raw.githubusercontent.com/*" ||
    context.parameters.url like "https://gist.githubusercontent.com/*" ||
    context.parameters.url like "https://*.gist.githubusercontent.com/*" ||
    context.parameters.url like "https://gist.github.com/*" ||
    context.parameters.url like "https://*.gist.github.com/*"
  )
};

@id("cag-018-credential-hunting-searches")
@source("policy.md#CAG-018")
forbid(
  principal,
  action == coding_agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "WebSearch" &&
  context has parameters &&
  context.parameters has query &&
  (
    context.parameters.query like "*password dump*" ||
    context.parameters.query like "*password dumps*" ||
    context.parameters.query like "*Password dump*" ||
    context.parameters.query like "*Password dumps*" ||
    context.parameters.query like "*leaked credential*" ||
    context.parameters.query like "*leaked credentials*" ||
    context.parameters.query like "*Leaked credential*" ||
    context.parameters.query like "*Leaked credentials*" ||
    context.parameters.query like "*exposed API key*" ||
    context.parameters.query like "*exposed API keys*" ||
    context.parameters.query like "*exposed api key*" ||
    context.parameters.query like "*exposed api keys*" ||
    context.parameters.query like "*Exposed API key*" ||
    context.parameters.query like "*Exposed API keys*" ||
    context.parameters.query like "*Exposed api key*" ||
    context.parameters.query like "*Exposed api keys*"
  )
};

@id("cag-019-private-key-output")
@source("policy.md#CAG-019")
forbid(
  principal,
  action == coding_agent::Action::"ToolOutput",
  resource
)
when {
  context.content like "*-----BEGIN *PRIVATE KEY-----*"
};

@id("cag-020-cloud-secret-output")
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