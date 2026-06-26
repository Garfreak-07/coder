from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from coder_workbench.harness_runtime import (
    HarnessRuntimeContext,
    HarnessRuntimeManager,
    default_llm_provider_profiles,
    normalize_llm_model,
    resolve_llm_provider_profile,
    run_harness_dry_run,
)
from coder_workbench.harness_runtime.openhands_provider import _llm_credentials


class HarnessProviderProfileTests(unittest.TestCase):
    def test_default_deepseek_profile_exists(self) -> None:
        profiles = default_llm_provider_profiles()
        profile = profiles["deepseek-default"]

        self.assertEqual(profile.provider, "deepseek")
        self.assertIn("LLM_API_KEY", profile.auth_env_candidates)
        self.assertIn("DEEPSEEK_API_KEY", profile.auth_env_candidates)
        self.assertEqual(profile.base_url, "https://api.deepseek.com")

    def test_env_compatibility_preserved(self) -> None:
        with (
            _env("CODER_LLM_PROVIDER_PROFILE", None),
            _env("LLM_API_KEY", "test-key"),
            _env("DEEPSEEK_API_KEY", None),
            _env("LLM_MODEL", "test-model"),
            _env("LLM_BASE_URL", "https://example.test/v1"),
        ):
            credentials = _llm_credentials()

        self.assertEqual(credentials["api_key"], "test-key")
        self.assertEqual(credentials["model"], "test-model")
        self.assertEqual(credentials["base_url"], "https://example.test/v1")

    def test_deepseek_model_normalization_preserved(self) -> None:
        profile = resolve_llm_provider_profile("deepseek-default")

        self.assertEqual(
            normalize_llm_model("deepseek-v4-flash", profile=profile, base_url=profile.base_url),
            "deepseek/deepseek-v4-flash",
        )
        self.assertEqual(
            normalize_llm_model("deepseek-chat", profile=profile, base_url=profile.base_url),
            "deepseek/deepseek-chat",
        )
        self.assertEqual(
            normalize_llm_model("deepseek/deepseek-chat", profile=profile, base_url=profile.base_url),
            "deepseek/deepseek-chat",
        )

    def test_profile_override_works(self) -> None:
        with _env("CODER_LLM_PROVIDER_PROFILE", "openai-compatible-env"):
            profile = resolve_llm_provider_profile()

        self.assertEqual(profile.id, "openai-compatible-env")
        self.assertEqual(profile.provider, "openai-compatible")

    def test_unknown_profile_fails_closed(self) -> None:
        with _env("CODER_LLM_PROVIDER_PROFILE", "missing-profile"):
            with self.assertRaisesRegex(ValueError, "unknown LLM provider profile"):
                resolve_llm_provider_profile()

            with (
                _env("LLM_API_KEY", "test-key"),
                patch("coder_workbench.harness_runtime.dry_run.importlib.util.find_spec", return_value=object()),
            ):
                report = run_harness_dry_run(_request())

        self.assertEqual(report.status, "blocked")
        self.assertEqual(_check(report, "llm_provider_profile").status, "blocked")

    def test_dry_run_reports_profile_metadata_safely(self) -> None:
        with (
            _env("CODER_LLM_PROVIDER_PROFILE", None),
            _env("LLM_API_KEY", "test-secret-key-value"),
            _env("DEEPSEEK_API_KEY", None),
            _env("LLM_MODEL", "deepseek-chat"),
            _env("LLM_BASE_URL", "https://api.deepseek.com/v1?api_key=test-secret-key-value"),
            patch("coder_workbench.harness_runtime.dry_run.importlib.util.find_spec", return_value=object()),
        ):
            report = run_harness_dry_run(_request())

        payload = report.model_dump_json()
        profile_check = _check(report, "llm_provider_profile")
        model_check = _check(report, "llm_model_base_url")
        credentials_check = _check(report, "llm_credentials")

        self.assertEqual(profile_check.metadata["llm_profile_id"], "deepseek-default")
        self.assertEqual(model_check.metadata["model"], "deepseek/deepseek-chat")
        self.assertEqual(model_check.metadata["base_url_host"], "api.deepseek.com")
        self.assertEqual(credentials_check.metadata["credential_source"], "LLM_API_KEY")
        self.assertNotIn("test-secret-key-value", payload)
        self.assertNotIn("api_key=test-secret-key-value", payload)


class _env:
    def __init__(self, key: str, value: str | None) -> None:
        self.key = key
        self.value = value
        self.old = os.environ.get(key)

    def __enter__(self) -> None:
        if self.value is None:
            os.environ.pop(self.key, None)
        else:
            os.environ[self.key] = self.value

    def __exit__(self, *_args: object) -> None:
        if self.old is None:
            os.environ.pop(self.key, None)
        else:
            os.environ[self.key] = self.old


def _request():
    manager = HarnessRuntimeManager()
    return manager._request(
        request_id="request-1",
        contract_id="conversation-harness",
        mode="workflow_supervisor",
        profile_id="openhands-workflow-supervisor-default",
        context=HarnessRuntimeContext(
            run_id="run-1",
            agent_id="planner",
            workflow_id="workflow-1",
            harness_id="conversation-harness",
            mode="workflow_supervisor",
            profile_id="openhands-workflow-supervisor-default",
        ),
        input_artifacts={"requested_artifact_type": "planner_order"},
    )


def _check(report, name: str):
    return next(check for check in report.checks if check.name == name)


if __name__ == "__main__":
    unittest.main()
