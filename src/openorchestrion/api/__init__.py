"""HTTP and WebSocket surface for OpenOrchestrion.

This package is the seam described in ``docs/api-contract.md``. The response
models in :mod:`.models` are the contract itself: FastAPI derives
``/openapi.json`` from them, so a client generated from that schema cannot drift
from what the backend returns.
"""

from .settings import Settings

__all__ = ["Settings"]
