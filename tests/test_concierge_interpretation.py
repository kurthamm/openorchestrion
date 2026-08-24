from __future__ import annotations

import pytest

from openorchestrion.ai import DeterministicConciergeProvider


@pytest.mark.asyncio
async def test_deterministic_provider_returns_readable_sentence() -> None:
    intent = await DeterministicConciergeProvider().interpret(
        "recognizable Christmas piano music for two hours"
    )

    assert intent.interpretation == (
        "The request is for familiar Christmas piano music for about 120 minutes."
    )
