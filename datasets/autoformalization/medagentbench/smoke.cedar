// Deterministic fixture for validating the replay adapter only.
// This is not an experimental policy and is never used as Generator output.
@id("smoke-default-pre")
@source("infrastructure")
permit(
    principal,
    action == medagentbench_agent::Action::"PreToolUse",
    resource
);

@id("smoke-default-output")
@source("infrastructure")
permit(
    principal,
    action == medagentbench_agent::Action::"ToolOutput",
    resource
);

@id("smoke-block-all-writes")
@source("test-fixture")
forbid(
    principal,
    action == medagentbench_agent::Action::"PreToolUse",
    resource
)
when {
    context has medical && context.medical.is_write
};
