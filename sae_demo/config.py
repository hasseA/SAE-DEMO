"""Configuration loading for the Nebius/NVIDIA provider.

Reads only from the environment (or an injectable mapping, for tests).
Never logs or persists the API key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional
import os

DEFAULT_NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
DEFAULT_NEBIUS_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


class MissingNebiusAPIKeyError(RuntimeError):
    """Raised when NEBIUS_API_KEY is not set in the environment."""


@dataclass(frozen=True)
class NebiusConfig:
    api_key: str
    base_url: str = DEFAULT_NEBIUS_BASE_URL
    model: str = DEFAULT_NEBIUS_MODEL

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"NebiusConfig(api_key='***redacted***', "
            f"base_url={self.base_url!r}, model={self.model!r})"
        )


def load_nebius_config(env: Optional[Mapping[str, str]] = None) -> NebiusConfig:
    """Load Nebius configuration from the environment.

    `env` is injectable for testing; defaults to `os.environ`.
    Raises MissingNebiusAPIKeyError if NEBIUS_API_KEY is not set/empty.
    """
    source = env if env is not None else os.environ

    api_key = source.get("NEBIUS_API_KEY", "")
    if not api_key:
        raise MissingNebiusAPIKeyError(
            "NEBIUS_API_KEY is not set. Set it in your environment or .env file."
        )

    base_url = source.get("NEBIUS_BASE_URL") or DEFAULT_NEBIUS_BASE_URL
    model = source.get("NEBIUS_MODEL") or DEFAULT_NEBIUS_MODEL

    return NebiusConfig(api_key=api_key, base_url=base_url, model=model)
