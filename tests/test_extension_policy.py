from __future__ import annotations

import unittest

from coder_workbench.extensions.policy import merge_extension_policy
from coder_workbench.extensions.runtime import ExtensionRuntime
from coder_workbench.tools import default_tool_registry


class ExtensionPolicyTests(unittest.TestCase):
    def test_merge_policy_uses_highest_risk_and_capability_permissions(self) -> None:
        class Capability:
            risk_level = "high"
            permissions = ("edit_files",)
            requires_approval = True

        policy = merge_extension_policy(
            operation_id="apply_patch",
            capability=Capability(),
            spec_risk_level="low",
            spec_requires_permission=False,
            input_requires_permission=False,
            input_requires_approval=False,
        )

        self.assertTrue(policy.known_operation)
        self.assertEqual(policy.risk_level, "high")
        self.assertEqual(policy.permissions, ["edit_files"])
        self.assertTrue(policy.requires_approval)

    def test_unknown_operation_policy_requires_approval(self) -> None:
        policy = merge_extension_policy(
            operation_id="unknown.op",
            capability=None,
            spec_risk_level="low",
            spec_requires_permission=False,
            input_requires_permission=False,
            input_requires_approval=False,
        )

        self.assertFalse(policy.known_operation)
        self.assertTrue(policy.requires_approval)

    def test_extension_runtime_exposes_registry_capability(self) -> None:
        runtime = ExtensionRuntime(registry=default_tool_registry())
        capability = runtime.capability("apply_patch")

        self.assertIsNotNone(capability)
        self.assertEqual(capability.risk_level, "high")
        self.assertTrue(capability.requires_approval)


if __name__ == "__main__":
    unittest.main()
