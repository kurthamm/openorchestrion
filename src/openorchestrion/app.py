from fastapi import FastAPI

from .models import PlaybackIntent

app = FastAPI(
    title="OpenOrchestrion",
    description="Networked MIDI music appliance",
    version="0.1.0-dev",
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> dict[str, object]:
    return {
        "phase": "bootstrap",
        "playing": False,
        "midi_devices": [],
        "ai": {"enabled": False},
    }


@app.post("/api/intent/validate")
async def validate_intent(intent: PlaybackIntent) -> PlaybackIntent:
    """Development endpoint demonstrating the AI/deterministic boundary."""
    return intent
