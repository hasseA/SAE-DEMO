"""Small, process-local cost safeguards for public demo inference calls.

This module deliberately provides only in-memory call ceilings. It is not an
account, authentication, or distributed rate-limit system. All state resets
when the server process restarts.
"""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


PER_CLIENT_LIMIT_ENV_VAR = "SAE_DEMO_MAX_INFERENCE_CALLS_PER_CLIENT"
TOTAL_LIMIT_ENV_VAR = "SAE_DEMO_MAX_INFERENCE_CALLS_TOTAL"

CLIENT_COOKIE_NAME = "sae_demo_session"

DEFAULT_PER_CLIENT_LIMIT = 20
DEFAULT_TOTAL_LIMIT = 200


class InferenceLimitExceededError(Exception):
    """A process-local client or server inference ceiling was reached."""


@dataclass(frozen=True)
class PublicDemoProtectionConfig:
    per_client_limit: int
    total_limit: int


def _positive_int(value: Optional[str], default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def load_public_demo_protection_config(
    env: Optional[Mapping[str, str]] = None,
) -> PublicDemoProtectionConfig:
    """Resolve safe protection settings from the environment.

    Positive call ceilings always remain active, with conservative defaults
    for missing or invalid values.
    """

    source = env if env is not None else os.environ
    return PublicDemoProtectionConfig(
        per_client_limit=_positive_int(
            source.get(PER_CLIENT_LIMIT_ENV_VAR), DEFAULT_PER_CLIENT_LIMIT
        ),
        total_limit=_positive_int(source.get(TOTAL_LIMIT_ENV_VAR), DEFAULT_TOTAL_LIMIT),
    )


class PublicDemoProtection:
    """Thread-safe, process-local session identities and call reservations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._issued_client_ids: set[str] = set()
        self._per_client_calls: dict[str, int] = {}
        self._total_calls = 0

    def identify_client(self, cookie_value: Optional[str]) -> Tuple[str, bool]:
        """Return a recognized server-issued id and whether a cookie is new."""

        with self._lock:
            if cookie_value and cookie_value in self._issued_client_ids:
                return cookie_value, False

            client_id = secrets.token_urlsafe(24)
            self._issued_client_ids.add(client_id)
            return client_id, True

    def reserve_inference(
        self,
        *,
        client_id: str,
        config: PublicDemoProtectionConfig,
    ) -> None:
        """Atomically reserve one provider-attempt slot.

        The reservation happens immediately before the provider path and is not
        refunded if the provider fails. This prevents repeated failed requests
        from bypassing the ceilings.
        """

        with self._lock:
            client_calls = self._per_client_calls.get(client_id, 0)
            if client_calls >= config.per_client_limit:
                raise InferenceLimitExceededError
            if self._total_calls >= config.total_limit:
                raise InferenceLimitExceededError

            self._per_client_calls[client_id] = client_calls + 1
            self._total_calls += 1

    def reset_for_tests(self) -> None:
        """Clear process-local state for isolated offline tests."""

        with self._lock:
            self._issued_client_ids.clear()
            self._per_client_calls.clear()
            self._total_calls = 0

    def counts_for_tests(self, client_id: str) -> Tuple[int, int]:
        """Return client/total reservations for offline assertions only."""

        with self._lock:
            return self._per_client_calls.get(client_id, 0), self._total_calls
