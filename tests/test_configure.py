from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import openorchestrion.configure as config
from openorchestrion.configure import (
    ConfigurationError,
    EnvironmentDocument,
    configure_files,
    show_configuration,
)


def _files(tmp_path: Path) -> tuple[Path, Path]:
    env = tmp_path / "openorchestrion.env"
    secrets = tmp_path / "openorchestrion.secrets.env"
    env.write_text(
        "# household appliance\n"
        "OPENORCHESTRION_LIBRARY_ROOT=/var/lib/openorchestrion/library\n"
        "OPENORCHESTRION_AI_PROVIDER=off\n"
        "FUTURE_SETTING=leave-me-alone\n",
        encoding="utf-8",
    )
    secrets.write_text("# service only\nOPENAI_API_KEY=sk-old-secret\n", encoding="utf-8")
    os.chmod(secrets, 0o640)
    return env, secrets


def test_environment_document_preserves_comments_unknown_keys_and_order(tmp_path: Path) -> None:
    env, _ = _files(tmp_path)
    rendered = EnvironmentDocument.read(env).updated(
        {
            "OPENORCHESTRION_AI_PROVIDER": "openai",
            "OPENORCHESTRION_AI_MODEL": "gpt-5.6-luna",
        }
    )

    assert rendered.startswith("# household appliance\n")
    assert "FUTURE_SETTING=leave-me-alone" in rendered
    assert "OPENORCHESTRION_AI_PROVIDER=openai" in rendered
    assert rendered.rstrip().endswith("OPENORCHESTRION_AI_MODEL=gpt-5.6-luna")


def test_configure_files_updates_both_documents_without_clobbering_unknowns(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)

    changed = configure_files(
        env_path=env,
        secrets_path=secrets,
        env_changes={
            "OPENORCHESTRION_AI_PROVIDER": "openai",
            "OPENORCHESTRION_AI_TIMEOUT_SECONDS": "10",
        },
        secret_changes={"OPENAI_API_KEY": "sk-new-secret"},
    )

    assert changed is True
    assert "FUTURE_SETTING=leave-me-alone" in env.read_text()
    assert "OPENORCHESTRION_AI_PROVIDER=openai" in env.read_text()
    assert "OPENORCHESTRION_AI_TIMEOUT_SECONDS=10" in env.read_text()
    assert "OPENAI_API_KEY=sk-new-secret" in secrets.read_text()
    assert secrets.stat().st_mode & 0o777 == 0o640


def test_show_configuration_redacts_secrets(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)

    shown = show_configuration(env, secrets)
    serialized = json.dumps(shown, sort_keys=True)

    assert shown["OPENAI_API_KEY"] == "<configured>"
    assert "sk-old-secret" not in serialized
    assert shown["FUTURE_SETTING"] == "leave-me-alone"


def test_malformed_secret_file_is_reported_not_hidden(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)
    secrets.write_text("this is not an assignment\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="expected KEY=value"):
        show_configuration(env, secrets)


def test_invalid_application_config_replaces_neither_file(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)
    before_env = env.read_bytes()
    before_secrets = secrets.read_bytes()

    with pytest.raises((ConfigurationError, ValueError), match="must be positive"):
        configure_files(
            env_path=env,
            secrets_path=secrets,
            env_changes={"OPENORCHESTRION_AI_TIMEOUT_SECONDS": "-1"},
            secret_changes={"OPENAI_API_KEY": "sk-should-not-land"},
        )

    assert env.read_bytes() == before_env
    assert secrets.read_bytes() == before_secrets


def test_second_file_failure_rolls_back_first_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, secrets = _files(tmp_path)
    before_env = env.read_bytes()
    before_secrets = secrets.read_bytes()

    def fail_secret_permissions(path: Path, *, secret: bool) -> None:
        if secret:
            raise OSError("simulated permission failure")

    monkeypatch.setattr(config, "_reference_permissions", fail_secret_permissions)

    with pytest.raises(ConfigurationError, match="configuration update failed"):
        configure_files(
            env_path=env,
            secrets_path=secrets,
            env_changes={"OPENORCHESTRION_AI_PROVIDER": "openai"},
            secret_changes={"OPENAI_API_KEY": "sk-new-secret"},
        )

    assert env.read_bytes() == before_env
    assert secrets.read_bytes() == before_secrets


def test_clear_key_removes_only_the_key(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)

    configure_files(
        env_path=env,
        secrets_path=secrets,
        env_changes={},
        secret_changes={"OPENAI_API_KEY": None},
    )

    text = secrets.read_text()
    assert "OPENAI_API_KEY" not in text
    assert "# service only" in text


def test_newline_in_secret_is_refused_before_write(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)
    before = secrets.read_bytes()

    with pytest.raises(ConfigurationError, match="may not contain a newline"):
        configure_files(
            env_path=env,
            secrets_path=secrets,
            env_changes={},
            secret_changes={"OPENAI_API_KEY": "line-one\nline-two"},
        )

    assert secrets.read_bytes() == before


def test_cli_show_json_never_prints_secret(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "openorchestrion.configure",
            "--env-file",
            str(env),
            "--secrets-file",
            str(secrets),
            "--show",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "sk-old-secret" not in result.stdout
    assert json.loads(result.stdout)["OPENAI_API_KEY"] == "<configured>"


def test_cli_key_file_requires_exactly_one_nonempty_line(tmp_path: Path) -> None:
    env, secrets = _files(tmp_path)
    keyfile = tmp_path / "key.txt"
    keyfile.write_text("first\nsecond\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "openorchestrion.configure",
            "--env-file",
            str(env),
            "--secrets-file",
            str(secrets),
            "--openai-key-file",
            str(keyfile),
            "--no-restart",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "exactly one non-empty line" in result.stderr
    assert "sk-old-secret" in secrets.read_text()
