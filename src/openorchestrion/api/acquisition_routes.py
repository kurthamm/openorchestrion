"""Guided discovery uses only the existing reviewed source registry and quality gate."""

import asyncio
import sys
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .errors import ApiError
from ..library.acquisition_job import read_job
from ..library.acquisition_sources import SOURCES

router = APIRouter(prefix='/api/library/acquisition')


class StartAcquisition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sources: list[str] = Field(min_length=1, max_length=5)


@router.get('/job')
async def job_status(request: Request):
    report = await asyncio.to_thread(read_job, request.app.state.settings.library_root.resolve())
    return {'job': report, 'supported': sys.platform.startswith('linux'),
            'sources': [{'key': s.key, 'label': s.label, 'genre': s.genre,
                         'license': s.license, 'reference': s.license_url,
                         'disabled': s.disabled} for s in SOURCES]}


@router.post('/job', status_code=202)
async def start_job(body: StartAcquisition, request: Request):
    # The LAN is trusted, but a page on another origin must not start downloads.
    origin = request.headers.get('origin')
    if (origin and urlsplit(origin).netloc != request.headers.get('host')) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise ApiError('request_invalid', 'Open Add music from this appliance.', status_code=403)
    if not sys.platform.startswith('linux'):
        raise ApiError('request_invalid', 'Guided acquisition requires the Linux appliance.', status_code=409)
    try:
        return await request.app.state.acquisition_jobs.start(body.sources)
    except ValueError as exc:
        raise ApiError('request_invalid', str(exc), status_code=422) from exc
    except (OSError, RuntimeError) as exc:
        raise ApiError('transport_conflict', str(exc), status_code=409) from exc
