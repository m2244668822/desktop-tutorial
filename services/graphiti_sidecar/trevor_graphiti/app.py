from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .config import SidecarConfig
from .redaction import redact_metadata_label, redact_text
from .runtime import TrevorGraphitiRuntime, load_runtime_secret


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    group_ids: list[str] = Field(default_factory=lambda: ['trevor'], max_length=10)
    limit: int = Field(default=10, ge=1, le=50)


class EpisodeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    episode_body: str = Field(min_length=1, max_length=50000)
    source_description: str = Field(min_length=1, max_length=300)
    reference_time: str = Field(min_length=10, max_length=80)
    episode_uuid: str = Field(min_length=36, max_length=36)
    group_id: str = Field(default='trevor', min_length=1, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_app(config: SidecarConfig | None = None) -> FastAPI:
    resolved_config = config or SidecarConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = await TrevorGraphitiRuntime.create(resolved_config)
        app.state.runtime = runtime
        app.state.internal_token = load_runtime_secret(
            'graphiti_token', 'TREVOR_GRAPHITI_TOKEN'
        )
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(
        title='Trevor Graphiti Sidecar',
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    async def require_internal_token(
        request: Request, authorization: str | None = Header(default=None)
    ) -> None:
        expected = str(getattr(request.app.state, 'internal_token', '') or '')
        if not expected:
            return
        supplied = str(authorization or '')
        if not supplied.startswith('Bearer ') or not secrets.compare_digest(
            supplied[7:], expected
        ):
            raise HTTPException(status_code=403, detail='forbidden')

    @app.get('/health')
    async def health(request: Request) -> dict[str, Any]:
        runtime = request.app.state.runtime
        payload = await runtime.gateway.health()
        extraction_model = (
            resolved_config.extraction_model
            if runtime.llm_provider == 'gemini'
            else resolved_config.nvidia_extraction_model
        )
        return {
            **payload,
            'graphiti_version': resolved_config.graphiti_version,
            'falkordblite_version': resolved_config.falkordblite_version,
            'models': {
                'extraction_provider': runtime.llm_provider,
                'extraction': extraction_model,
                'rerank_provider': runtime.rerank_provider,
                'rerank': (
                    resolved_config.rerank_model
                    if runtime.rerank_provider == 'gemini'
                    else 'deterministic-lexical'
                ),
                'embedding': resolved_config.embedding_model,
                'max_output_tokens': resolved_config.llm_max_tokens,
                'timeout_seconds': resolved_config.llm_timeout_seconds,
            },
        }

    @app.post('/v1/search', dependencies=[Depends(require_internal_token)])
    async def search(payload: SearchRequest, request: Request) -> dict[str, Any]:
        query, redactions = redact_text(payload.query)
        items = await request.app.state.runtime.gateway.search(
            query, group_ids=payload.group_ids, limit=payload.limit
        )
        return {'ok': True, 'items': items, 'redactions': redactions}

    @app.post('/v1/episodes', dependencies=[Depends(require_internal_token)])
    async def add_episode(payload: EpisodeRequest, request: Request) -> dict[str, Any]:
        body, redactions = redact_text(payload.episode_body)
        source, source_redactions = redact_text(payload.source_description)
        source_role, source_role_redactions = redact_metadata_label(
            payload.metadata.get('source_role', ''), limit=80
        )
        capability, capability_redactions = redact_metadata_label(
            payload.metadata.get('capability_mode', ''), limit=40
        )
        if source_role:
            source = f'{source};source_role={source_role[:80]}'
        if capability:
            source = f'{source};capability={capability[:40]}'
        await request.app.state.runtime.gateway.add_episode(
            name=payload.name,
            episode_body=body,
            source_description=source,
            reference_time=payload.reference_time,
            episode_uuid=payload.episode_uuid,
            group_id=payload.group_id,
        )
        return {
            'ok': True,
            'redactions': (
                redactions
                + source_redactions
                + source_role_redactions
                + capability_redactions
            ),
        }

    return app


__all__ = ['create_app']
