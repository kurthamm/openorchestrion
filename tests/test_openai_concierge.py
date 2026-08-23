from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from openorchestrion import appliance
from openorchestrion.ai_runtime import create_configured_concierge, describe_intent
from openorchestrion.api.settings import Settings
from openorchestrion.models import PlaybackIntent


class FakeResponses:
    def __init__(self, *, parsed: PlaybackIntent | None = None, refusal: str | None = None) -> None:
        self.parsed = parsed
        self.refusal = refusal
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        output = []
        if self.refusal is not None:
            output = [
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="refusal", refusal=self.refusal)],
                )
            ]
        return SimpleNamespace(output_parsed=self.parsed, output=output)


class FakeOpenAIClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "library_root": tmp_path / "library",
        "catalog_db": tmp_path / "library" / "catalog.db",
        "history_db": tmp_path / "history.db",
        "ai_provider": "openai",
        "ai_model": "gpt-5.6-luna",
        "ai_timeout_seconds": 7.5,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_openai_structured_output_becomes_validated_intent(tmp_path: Path) -> None:
    parsed = PlaybackIntent(
        themes=["Christmas", "dinner"],
        instrumentation=["piano"],
        familiarity="high",
        duration_minutes=120,
    )
    responses = FakeResponses(parsed=parsed)
    concierge = create_configured_concierge(
        _settings(tmp_path),
        environ={"OPENAI_API_KEY": "sk-test-never-sent"},
        openai_client=FakeOpenAIClient(responses),
    )

    result = await concierge.interpret("recognizable Christmas piano music for dinner for two hours")

    assert result.provider == "openai:gpt-5.6-luna"
    assert result.fallback_used is False
    assert result.intent.duration_minutes == 120
    assert result.intent.themes == ["Christmas", "dinner"]
    assert result.intent.interpretation is not None
    assert result.intent.interpretation.endswith(".")
    assert responses.calls[0]["text_format"] is PlaybackIntent
    assert responses.calls[0]["model"] == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_refinement_supplies_current_intent_and_preserves_hard_tags(tmp_path: Path) -> None:
    current = PlaybackIntent(
        themes=["dinner"],
        include_tags=["piano"],
        exclude_tags=["dramatic"],
        energy="low",
    )
    parsed = current.model_copy(deep=True)
    parsed.energy = "medium"
    responses = FakeResponses(parsed=parsed)
    concierge = create_configured_concierge(
        _settings(tmp_path),
        environ={"OPENAI_API_KEY": "sk-test"},
        openai_client=FakeOpenAIClient(responses),
    )

    result = await concierge.interpret("more upbeat", current_intent=current)

    assert result.fallback_used is False
    assert result.intent.include_tags == ["piano"]
    assert result.intent.exclude_tags == ["dramatic"]
    sent = str(responses.calls[0]["input"])
    assert "Current validated intent JSON" in sent
    assert "dramatic" in sent
    assert "more upbeat" in sent


@pytest.mark.asyncio
async def test_provider_cannot_drop_hard_tags_during_refinement(tmp_path: Path) -> None:
    current = PlaybackIntent(include_tags=["piano"], exclude_tags=["dramatic"], energy="low")
    responses = FakeResponses(parsed=PlaybackIntent(energy="high"))
    concierge = create_configured_concierge(
        _settings(tmp_path),
        environ={"OPENAI_API_KEY": "sk-test"},
        openai_client=FakeOpenAIClient(responses),
    )

    result = await concierge.interpret("more upbeat", current_intent=current)

    assert result.fallback_used is True
    assert "dropped a hard include tag" in (result.primary_error or "")
    assert result.intent.include_tags == ["piano"]
    assert result.intent.exclude_tags == ["dramatic"]


@pytest.mark.asyncio
async def test_provider_refusal_falls_back_offline(tmp_path: Path) -> None:
    responses = FakeResponses(refusal="I cannot help with that request.")
    concierge = create_configured_concierge(
        _settings(tmp_path),
        environ={"OPENAI_API_KEY": "sk-test"},
        openai_client=FakeOpenAIClient(responses),
    )

    result = await concierge.interpret("Christmas piano")

    assert result.fallback_used is True
    assert result.provider == "deterministic-fallback"
    assert "refused" in (result.primary_error or "").casefold()
    assert "Christmas" in result.intent.themes


@pytest.mark.asyncio
async def test_provider_network_error_falls_back_offline(tmp_path: Path) -> None:
    responses = FakeResponses(parsed=None)
    responses.error = TimeoutError("network timeout")
    concierge = create_configured_concierge(
        _settings(tmp_path),
        environ={"OPENAI_API_KEY": "sk-test"},
        openai_client=FakeOpenAIClient(responses),
    )

    result = await concierge.interpret("relaxing classical")

    assert result.fallback_used is True
    assert result.intent.genres == ["classical"]
    assert "TimeoutError" in (result.primary_error or "")


@pytest.mark.asyncio
async def test_configured_provider_without_key_uses_fallback_without_client_call(tmp_path: Path) -> None:
    responses = FakeResponses(parsed=PlaybackIntent())
    concierge = create_configured_concierge(
        _settings(tmp_path),
        environ={},
        openai_client=FakeOpenAIClient(responses),
    )

    result = await concierge.interpret("ragtime")

    assert concierge.primary is None
    assert responses.calls == []
    assert result.fallback_used is True
    assert "api_key_missing" in (result.primary_error or "")
    assert result.intent.genres == ["ragtime"]


def test_settings_do_not_store_or_expose_openai_api_key(tmp_path: Path) -> None:
    secret = "sk-super-secret-value"
    settings = Settings.from_env(
        {
            "OPENORCHESTRION_LIBRARY_ROOT": str(tmp_path / "library"),
            "OPENORCHESTRION_AI_PROVIDER": "openai",
            "OPENORCHESTRION_AI_MODEL": "gpt-5.6-luna",
            "OPENORCHESTRION_AI_TIMEOUT_SECONDS": "12",
            "OPENAI_API_KEY": secret,
        }
    )

    assert settings.ai_provider == "openai"
    assert settings.ai_timeout_seconds == 12.0
    assert secret not in repr(settings)
    assert secret not in repr(asdict(settings))
    assert "api_key" not in asdict(settings)


@pytest.mark.parametrize("value", ["0", "-1", "nope"])
def test_settings_reject_invalid_ai_timeout(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError):
        Settings.from_env(
            {
                "OPENORCHESTRION_LIBRARY_ROOT": str(tmp_path / "library"),
                "OPENORCHESTRION_AI_TIMEOUT_SECONDS": value,
            }
        )


def test_deterministic_description_is_a_complete_sentence() -> None:
    text = describe_intent(
        PlaybackIntent(
            themes=["Christmas"],
            instrumentation=["piano"],
            familiarity="high",
            duration_minutes=120,
        )
    )
    assert text == "The request is for familiar Christmas piano music for about 120 minutes."


def test_appliance_packaging_keeps_provider_secret_service_only(tmp_path: Path) -> None:
    files = {path.name: path for path in appliance.export_deployment_files(tmp_path / "deploy")}
    service = files["openorchestrion.service"].read_text()
    environment = files["openorchestrion.env"].read_text()
    installer = files["install-appliance.sh"].read_text()

    assert "openorchestrion.secrets.env" in service
    assert "OPENAI_API_KEY" not in environment
    assert "OPENORCHESTRION_AI_PROVIDER=" in environment
    assert "--with-openai" in installer
    assert "chmod 0640" in installer
    assert "OPENAI_API_KEY" in installer
