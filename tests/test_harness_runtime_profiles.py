import unittest

from coder_workbench.harness_runtime import (
    HarnessBindings,
    HarnessRunResult,
    HarnessRuntimeContext,
    HarnessRuntimeManager,
    default_harness_runtime_profiles,
    harness_contract_for_id,
)
from coder_workbench.harness_runtime.profiles import INTERNAL_FALLBACK_PROVIDER_ID


class HarnessRuntimeProfileTests(unittest.TestCase):
    def test_default_bindings_point_to_openhands_profiles(self) -> None:
        bindings = HarnessBindings()

        self.assertEqual(bindings.planning_chat.profile_id, "openhands-planning-chat-default")
        self.assertEqual(bindings.workflow_supervisor.profile_id, "openhands-workflow-supervisor-default")
        self.assertEqual(bindings.task_execution.profile_id, "openhands-task-executor-default")

    def test_default_profiles_match_their_canonical_contracts(self) -> None:
        profiles = default_harness_runtime_profiles()

        self.assertEqual(
            sorted(profiles),
            [
                "internal-fallback-planning-chat",
                "internal-fallback-task-executor",
                "internal-fallback-workflow-supervisor",
                "openhands-planning-chat-default",
                "openhands-task-executor-default",
                "openhands-workflow-supervisor-default",
            ],
        )
        for profile in profiles.values():
            contract = harness_contract_for_id(profile.harness_id)
            self.assertIn(profile.mode, contract.modes)
            self.assertTrue(profile.allowed_artifacts)

    def test_manager_uses_internal_fallback_when_openhands_is_disabled(self) -> None:
        events: list[tuple[str, dict]] = []

        def emit(event_type: str, message: str, **payload: object) -> None:
            events.append((event_type, {"message": message, **payload}))

        manager = HarnessRuntimeManager()
        context = HarnessRuntimeContext(
            run_id="run-1",
            agent_id="planner",
            workflow_id="workflow-1",
            harness_id="conversation-harness",
            mode="workflow_supervisor",
            profile_id="openhands-workflow-supervisor-default",
        )

        result = manager.run_workflow_supervisor(context=context, emit=emit)

        self.assertIsInstance(result, HarnessRunResult)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "fallback_provider_unconfigured")
        self.assertEqual(events[0][0], "harness_runtime.fallback.unconfigured")

    def test_manager_can_run_explicit_internal_fallback_profile(self) -> None:
        manager = HarnessRuntimeManager()
        profile = manager.profile_for_id("internal-fallback-task-executor")

        self.assertEqual(profile.provider_id, INTERNAL_FALLBACK_PROVIDER_ID)
        self.assertEqual(profile.mode, "task_execution")


if __name__ == "__main__":
    unittest.main()
