from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.harness_runtime import evaluate_harness_permission


class HarnessPermissionTests(unittest.TestCase):
    def test_planner_cannot_write_files(self) -> None:
        decision = evaluate_harness_permission(
            mode="workflow_supervisor",
            harness_id="conversation-harness",
            action_type="write_file",
            file_path="src/app.py",
            sandbox_root="F:\\sandbox",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "planner_read_only_violation")

    def test_planner_cannot_run_commands(self) -> None:
        decision = evaluate_harness_permission(
            mode="workflow_supervisor",
            harness_id="conversation-harness",
            action_type="run_command",
            command="python -m unittest discover tests",
            sandbox_root="F:\\sandbox",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "planner_read_only_violation")

    def test_executor_denies_outside_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as sandbox, tempfile.TemporaryDirectory() as outside:
            decision = evaluate_harness_permission(
                mode="task_execution",
                harness_id="task-execution-harness",
                action_type="write_file",
                file_path=str(Path(outside) / "app.py"),
                sandbox_root=sandbox,
            )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "executor_outside_sandbox")

    def test_executor_allows_safe_sandbox_path(self) -> None:
        with tempfile.TemporaryDirectory() as sandbox:
            decision = evaluate_harness_permission(
                mode="task_execution",
                harness_id="task-execution-harness",
                action_type="write_file",
                file_path=str(Path(sandbox) / "src" / "app.py"),
                sandbox_root=sandbox,
            )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "allowed")

    def test_executor_denies_sensitive_paths(self) -> None:
        sensitive_paths = [
            ".ssh/id_rsa",
            ".env",
            ".env.local",
            ".aws/credentials",
            ".aws/config",
            ".config/gcloud/application_default_credentials.json",
            ".azure/accessTokens.json",
            ".gnupg/private-keys-v1.d/key",
            ".docker/config.json",
            ".kube/config",
            ".openharness/credentials.json",
            ".openharness/copilot_auth.json",
            "id_ed25519",
        ]
        with tempfile.TemporaryDirectory() as sandbox:
            for file_path in sensitive_paths:
                with self.subTest(file_path=file_path):
                    decision = evaluate_harness_permission(
                        mode="task_execution",
                        harness_id="task-execution-harness",
                        action_type="write_file",
                        file_path=str(Path(sandbox) / file_path),
                        sandbox_root=sandbox,
                    )
                    self.assertFalse(decision.allowed)
                    self.assertEqual(decision.code, "sensitive_path_denied")

    def test_executor_does_not_over_deny_normal_project_names(self) -> None:
        normal_paths = [
            "src/tokenizer.py",
            "tests/credentials_test.py",
            "tests/test_credentials_schema.py",
        ]
        with tempfile.TemporaryDirectory() as sandbox:
            for file_path in normal_paths:
                with self.subTest(file_path=file_path):
                    decision = evaluate_harness_permission(
                        mode="task_execution",
                        harness_id="task-execution-harness",
                        action_type="write_file",
                        file_path=str(Path(sandbox) / file_path),
                        sandbox_root=sandbox,
                    )
                    self.assertTrue(decision.allowed)

    def test_executor_denies_commit_push_deploy_commands(self) -> None:
        commands = [
            "git commit -m test",
            "git push origin main",
            "git tag v1",
            "gh release create v1",
            "npm publish",
            "pnpm publish",
            "yarn publish",
            "twine upload dist/*",
            "docker push repo/image:tag",
            "kubectl apply -f deploy.yaml",
            "kubectl delete -f deploy.yaml",
            "terraform apply -auto-approve",
            "terraform destroy -auto-approve",
            "vercel deploy --prod",
            "netlify deploy --prod",
        ]
        with tempfile.TemporaryDirectory() as sandbox:
            for command in commands:
                with self.subTest(command=command):
                    decision = evaluate_harness_permission(
                        mode="task_execution",
                        harness_id="task-execution-harness",
                        action_type="run_command",
                        command=command,
                        sandbox_root=sandbox,
                    )
                    self.assertFalse(decision.allowed)
                    self.assertEqual(decision.code, "commit_push_deploy_denied")

    def test_executor_denies_dangerous_and_interactive_commands(self) -> None:
        expected = {
            "rm -rf /": "dangerous_command_denied",
            "format c:": "dangerous_command_denied",
            "shutdown /s": "dangerous_command_denied",
            "reboot": "dangerous_command_denied",
            "vim src/app.py": "user_interaction_denied",
            "less README.md": "user_interaction_denied",
            "read -p confirm answer": "user_interaction_denied",
            "pause": "user_interaction_denied",
        }
        with tempfile.TemporaryDirectory() as sandbox:
            for command, code in expected.items():
                with self.subTest(command=command):
                    decision = evaluate_harness_permission(
                        mode="task_execution",
                        harness_id="task-execution-harness",
                        action_type="run_command",
                        command=command,
                        sandbox_root=sandbox,
                    )
                    self.assertFalse(decision.allowed)
                    self.assertEqual(decision.code, code)

    def test_executor_allows_safe_checks(self) -> None:
        commands = [
            "python -m unittest discover tests",
            "pytest",
            "npm run build",
            "npm test",
            "git diff",
            "git status",
            "git log",
        ]
        with tempfile.TemporaryDirectory() as sandbox:
            for command in commands:
                with self.subTest(command=command):
                    decision = evaluate_harness_permission(
                        mode="task_execution",
                        harness_id="task-execution-harness",
                        action_type="run_command",
                        command=command,
                        sandbox_root=sandbox,
                    )
                    self.assertTrue(decision.allowed)
                    self.assertEqual(decision.code, "allowed")


if __name__ == "__main__":
    unittest.main()
