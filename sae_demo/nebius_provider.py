"""Minimal Nebius/NVIDIA provider adapter.

Always sends the confirmed non-reasoning configuration for
nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B on the Nebius Token Factory
endpoint (https://api.tokenfactory.nebius.com/v1/). Treats any
non-null `reasoning` field in the response as a configuration/safety
warning rather than a fatal error, since a future model or endpoint
change could silently start returning reasoning again.

Never logs or includes the API key or any raw exception text (which
could contain request headers) in error messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from openai import OpenAI

from .config import NebiusConfig

logger = logging.getLogger(__name__)

# Confirmed live on https://api.tokenfactory.nebius.com/v1/ for
# nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B: disables reasoning output and
# keeps completion_tokens bounded to the visible answer instead of
# being consumed by internal reasoning tokens. Always sent; not
# optional per-call.
NON_REASONING_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


class NebiusProviderError(RuntimeError):
    """Raised when a request to the Nebius provider fails.

    The message intentionally contains only the exception's class
    name, never str(exc), to avoid leaking secrets that might appear
    in an underlying HTTP client's error text (headers, request
    bodies, etc.).
    """


@dataclass(frozen=True)
class NebiusCompletionResult:
    content: Optional[str]
    reasoning: Optional[str]
    finish_reason: Optional[str]
    completion_tokens: Optional[int]
    reasoning_warning: bool


class NebiusProvider:
    """Thin adapter over the OpenAI-compatible Nebius Token Factory API."""

    def __init__(self, config: NebiusConfig, *, client: Optional[Any] = None) -> None:
        self._config = config
        self._client = client or OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"NebiusProvider(model={self._config.model!r}, "
            f"base_url={self._config.base_url!r})"
        )

    def complete(
        self,
        messages: Iterable[Mapping[str, str]],
        *,
        max_tokens: int = 100,
    ) -> NebiusCompletionResult:
        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=list(messages),
                max_tokens=max_tokens,
                extra_body=NON_REASONING_EXTRA_BODY,
            )
        except Exception as exc:  # noqa: BLE001 - intentionally broad, re-raised safely
            raise NebiusProviderError(
                f"Nebius request failed: {exc.__class__.__name__}"
            ) from None

        choice = response.choices[0]
        message = choice.message
        reasoning = getattr(message, "reasoning", None)

        reasoning_warning = reasoning is not None
        if reasoning_warning:
            logger.warning(
                "Nebius response included a non-null 'reasoning' field even "
                "though the non-reasoning configuration was sent; treat this "
                "as a configuration/safety warning."
            )

        return NebiusCompletionResult(
            content=message.content,
            reasoning=reasoning,
            finish_reason=choice.finish_reason,
            completion_tokens=getattr(response.usage, "completion_tokens", None),
            reasoning_warning=reasoning_warning,
        )
