import json
import os
import subprocess
import sys

import pytest

from verifigen.config import ModelSettings


def test_local_configuration_preserves_explicit_environment_and_hides_key(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text("DASHSCOPE_API_KEY=private-fixture\nDASHSCOPE_MODEL=file-model\n")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_MODEL", "environment-model")
    settings = ModelSettings.from_env(env_file)
    assert settings.model == "environment-model"
    assert settings.api_key == "private-fixture"
    assert "private-fixture" not in repr(settings)


def test_missing_api_key_fails_before_request():
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        ModelSettings(api_key="").stack()


def test_current_stack_defaults_to_json_compatible_mode_and_supports_role_choice():
    stack = ModelSettings(api_key="test-secret").stack(judge_model="separate-judge")
    assert stack.generator.extra_body == {"enable_thinking": False}
    assert stack.judge.generator.model == "separate-judge"
    assert stack.generator.model == stack.repairer.generator.model == "qwen3.5-flash"
    assert not stack.judge.validate_quotes
    thinking = ModelSettings(api_key="test-secret").stack(enable_thinking=True)
    assert thinking.generator.extra_body == {"enable_thinking": True, "thinking_budget": 1024}


def test_structured_output_capacity_is_forwarded_to_each_runtime_role():
    stack = ModelSettings(api_key="test-secret").stack(
        judge_strategy="claims",
        max_output_tokens=8192,
    )
    assert stack.generator.max_output_tokens == 8192
    assert stack.judge.generator.max_output_tokens == 8192
    assert stack.repairer.generator.max_output_tokens == 8192


def test_doctor_reports_configuration_without_credentials(tmp_path):
    env_file = tmp_path / "local.env"
    env_file.write_text("DASHSCOPE_API_KEY=private-fixture\nDASHSCOPE_MODEL=test-model\n")
    result = subprocess.run(
        [sys.executable, "-m", "verifigen.cli", "doctor", "--env-file", str(env_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["api_key_configured"]
    assert "private-fixture" not in result.stdout + result.stderr


def test_doctor_exit_status_identifies_missing_configuration(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "verifigen.cli",
            "doctor",
            "--env-file",
            str(tmp_path / "absent.env"),
        ],
        env={k: v for k, v in os.environ.items() if k != "DASHSCOPE_API_KEY"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert not json.loads(result.stdout)["api_key_configured"]
