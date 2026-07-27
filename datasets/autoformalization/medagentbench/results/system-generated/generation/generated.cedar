@id("default-prompt-permit")
@source("infrastructure")
permit(
  principal,
  action == medagentbench_agent::Action::"Prompt",
  resource
);

@id("default-pretooluse-permit")
@source("infrastructure")
permit(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
);

@id("default-tooloutput-permit")
@source("infrastructure")
permit(
  principal,
  action == medagentbench_agent::Action::"ToolOutput",
  resource
);

@id("mab-2-1-require-patient-identifier")
@source("policy.md§2.1")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  (
    context.tool == "get_request" ||
    context.tool == "post_request" ||
    context.tool == "get_patient" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  !context.medical.patient_id_present &&
  context.medical.current_patient_id == "" &&
  !context.medical.query_has_identifier
};

@id("mab-2-2-stop-after-multiple-patient-matches")
@source("policy.md§2.2")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "get_request" ||
    context.tool == "post_request" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request" ||
    (context.tool == "get_patient" && !context.medical.query_has_identifier)
  ) &&
  context.session.last_get_patient_returned_multiple
};

@id("mab-2-3-block-unresolved-patient-mismatch")
@source("policy.md§2.3")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has session &&
  (
    context.tool == "get_request" ||
    context.tool == "post_request" ||
    context.tool == "get_patient" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.session.current_call_patient_mismatch
};

@id("mab-2-4-confirm-patient-before-write")
@source("policy.md§2.4")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "post_request" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.medical.is_write &&
  (!context.session.last_assistant_restated_patient || !context.session.user_confirmed_write)
};

@id("mab-2-5-one-patient-per-session")
@source("policy.md§2.5")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "get_request" ||
    context.tool == "post_request" ||
    context.tool == "get_patient" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.session.current_call_patient_unseen &&
  context.session.established_patient_id != "" &&
  context.medical.current_patient_id != "" &&
  context.medical.current_patient_id != context.session.established_patient_id
};

@id("mab-3-1-require-patient-care-purpose")
@source("policy.md§3.1")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  (
    context.tool == "get_request" ||
    context.tool == "get_patient" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure"
  ) &&
  (!context.medical.purpose_present || !context.medical.purpose_is_patient_care)
};

@id("mab-3-2-refuse-non-care-phi")
@source("policy.md§3.2")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  (
    context.tool == "get_request" ||
    context.tool == "get_patient" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure"
  ) &&
  context.medical.purpose_present &&
  !context.medical.purpose_is_patient_care
};

@id("mab-5-1-no-write-without-confirmation")
@source("policy.md§5.1")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "post_request" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.medical.is_write &&
  !context.session.pending_write_confirmed
};

@id("mab-5-2-write-requires-resolved-linked-patient")
@source("policy.md§5.2")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "post_request" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.medical.is_write &&
  (
    context.session.established_patient_id == "" ||
    context.session.current_call_patient_mismatch ||
    context.medical.current_patient_id == "" ||
    context.medical.current_patient_id != context.session.established_patient_id
  )
};

@id("mab-5-6-confirm-duplicate-write")
@source("policy.md§5.6")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "post_request" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.medical.is_write &&
  context.session.current_call_is_duplicate &&
  !context.session.user_confirmed_write
};

@id("mab-5-11-write-subject-must-reference-patient")
@source("policy.md§5.11")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  (
    context.tool == "post_request" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.medical.is_write &&
  (!context.medical.subject_reference_present || !context.medical.subject_is_patient || context.medical.current_patient_id == "")
};

@id("mab-5-12-medication-request-requires-allergy-check")
@source("policy.md§5.12")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "post_medication_request" ||
    (context.tool == "post_request" && context.medical.resource_type == "MedicationRequest")
  ) &&
  context.medical.is_write &&
  !context.session.user_confirmed_allergy_check
};

@id("mab-6-3-stop-after-tool-error")
@source("policy.md§6.3")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has session &&
  (
    context.tool == "get_request" ||
    context.tool == "post_request" ||
    context.tool == "get_patient" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.session.last_tool_error
};

@id("mab-6-5-no-unsafe-write-retry")
@source("policy.md§6.5")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "post_request" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.medical.is_write &&
  context.session.current_call_retries_failed_write &&
  !context.session.user_confirmed_write
};

@id("mab-7-2-confirm-planned-write-summary")
@source("policy.md§7.2")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  context has session &&
  (
    context.tool == "post_request" ||
    context.tool == "post_observation" ||
    context.tool == "post_medication_request" ||
    context.tool == "post_service_request"
  ) &&
  context.medical.is_write &&
  (!context.session.pending_write_confirmed || !context.session.user_confirmed_write)
};

@id("mab-8-3-refuse-outside-care-purpose")
@source("policy.md§8.3")
forbid(
  principal,
  action == medagentbench_agent::Action::"PreToolUse",
  resource
)
when {
  context has medical &&
  (
    context.tool == "get_request" ||
    context.tool == "get_patient" ||
    context.tool == "get_condition" ||
    context.tool == "get_observation" ||
    context.tool == "get_medication_request" ||
    context.tool == "get_procedure"
  ) &&
  !context.medical.purpose_is_patient_care
};