"""HTTP router for /api/brain/ask."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from axiom.api.brain_ask import (
    MAX_QUESTION_LENGTH,
    MAX_TOP_K,
    MIN_QUESTION_LENGTH,
    ChatCompletionError,
    LLMProviderKeyNotFound,
    UnknownLLMProvider,
    VaultCorrupt,
    VaultLocked,
    ask_brain,
)
from axiom.studio.rate_limit import (
    RateLimitExceededError,
    ask_limiter,
    rate_limit_key,
)

router = APIRouter()


def _bearer_token(request: Request) -> str | None:
    """Extract the bearer token from the Authorization header, if any."""
    header = request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


class AskIn(BaseModel):
    question: str = Field(min_length=MIN_QUESTION_LENGTH, max_length=MAX_QUESTION_LENGTH)
    provider: Literal["anthropic", "openai"] | None = None
    model: str | None = Field(default=None, max_length=120)
    mode: Literal["hybrid", "lexical", "semantic", "graph"] = "hybrid"
    top_k: int = Field(default=8, ge=1, le=MAX_TOP_K)
    entity_types: list[str] | None = None
    cluster_id: str | None = Field(default=None, max_length=120)
    max_tokens: int = Field(default=1024, ge=64, le=4096)


def _session_factory(request: Request) -> Any:
    return request.app.state.SessionLocal


@router.post("/api/brain/ask")
def post_brain_ask(body: AskIn, request: Request) -> dict[str, Any]:
    client_host = request.client.host if request.client else None
    key = rate_limit_key(_bearer_token(request), client_host)
    try:
        ask_limiter.check(key, body.max_tokens)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=exc.detail,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    try:
        with _session_factory(request)() as session:
            result = ask_brain(
                session,
                question=body.question,
                provider=body.provider,
                model=body.model,
                mode=body.mode,
                top_k=body.top_k,
                entity_types=body.entity_types,
                cluster_id=body.cluster_id,
                max_tokens=body.max_tokens,
            )
    except UnknownLLMProvider as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMProviderKeyNotFound as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc) or "no LLM provider key registered",
        ) from exc
    except VaultLocked as exc:
        raise HTTPException(status_code=503, detail="vault key unavailable") from exc
    except VaultCorrupt as exc:
        raise HTTPException(
            status_code=500,
            detail="stored provider key cannot be decrypted",
        ) from exc
    except ChatCompletionError as exc:
        status = {
            "auth_error": 502,
            "rate_limited": 429,
            "network_error": 502,
        }.get(exc.status, 502)
        raise HTTPException(status_code=status, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.to_dict()
