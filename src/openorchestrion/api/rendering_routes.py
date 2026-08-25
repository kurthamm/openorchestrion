"""Read-only rendering vocabulary for the browser control surface."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from ..midi import GM_PROGRAM_NAMES
from ..playback import RenderingMode

router = APIRouter(prefix="/api")


class RenderingProgramOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = Field(ge=0, le=127)
    name: str = Field(min_length=1)


class RenderingOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modes: list[RenderingMode]
    piano_programs: list[RenderingProgramOption]
    programs: list[RenderingProgramOption]
    percussion_channel: int = Field(ge=0, le=15)


@router.get("/rendering/options", response_model=RenderingOptionsResponse)
async def rendering_options() -> RenderingOptionsResponse:
    programs = [
        RenderingProgramOption(value=value, name=name)
        for value, name in enumerate(GM_PROGRAM_NAMES)
    ]
    return RenderingOptionsResponse(
        modes=list(RenderingMode),
        piano_programs=programs[:8],
        programs=programs,
        percussion_channel=9,
    )


__all__ = ["router"]
