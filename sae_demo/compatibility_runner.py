"""Synthetic compatibility runner — Memory OFF only.

Replays a frozen `Scenario` through the Nebius/NVIDIA provider one
segment at a time, maintaining conversation history across turns, and
records a neutral interaction trace: exact user text sent, exact
assistant text returned, and structural/protocol metadata (finish
reason, model label, reasoning-field presence, token usage) for each
turn.

This is a compatibility harness, not a scientific experiment: it
performs no emotional scoring or interpretation, does not load any
Emotional Memory, and does not implement recognition, activation, or
an A/B/C comparison. Memory ON (supplying an Emotional Memory export
as context) is explicitly out of scope for this stage — every run
here is Memory OFF: only the scenario's own segment text is ever sent.

Independent of the Nebius provider's internals beyond its public
`complete()` method; independent of any UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .nebius_provider import NebiusProvider, NebiusProviderError
from .scenario import MODE_FROZEN, Scenario
from .scenario_engine import RunTrace, ScenarioEngine

# Generic, public-safe system message. Not derived from, and does not
# resemble, any private SAE system prompt or Frame instrument.
DEFAULT_SYSTEM_MESSAGE = (
    "You are participating in a short scripted conversation. Respond "
    "naturally and concisely to each message as it arrives."
)

DEFAULT_MAX_TOKENS = 200


class CompatibilityRunnerError(RuntimeError):
    """Raised when the compatibility runner cannot complete a run."""


class NotAFrozenScenarioError(CompatibilityRunnerError):
    """Raised when a non-frozen scenario is passed to the runner.

    This stage only replays frozen, reproducible runs; interactive
    editing during a live compatibility check is out of scope.
    """


@dataclass(frozen=True)
class TurnMetadata:
    """Provider-facing metadata captured for one exchanged turn.

    Contains no emotional scoring or interpretation — only structural
    request/response metadata.
    """

    segment_id: str
    role: str
    user_text_sent: str
    assistant_text: Optional[str]
    finish_reason: Optional[str]
    model: Optional[str]
    reasoning_present: bool
    completion_tokens: Optional[int]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "role": self.role,
            "user_text_sent": self.user_text_sent,
            "assistant_text": self.assistant_text,
            "finish_reason": self.finish_reason,
            "model": self.model,
            "reasoning_present": self.reasoning_present,
            "completion_tokens": self.completion_tokens,
            "error": self.error,
        }


@dataclass(frozen=True)
class CompatibilityRunResult:
    """The outcome of one Memory-OFF compatibility run."""

    scenario_id: str
    scenario_title: str
    mode: str
    completed: bool
    turns: Tuple[TurnMetadata, ...]
    engine_trace: RunTrace

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "scenario_title": self.scenario_title,
            "mode": self.mode,
            "completed": self.completed,
            "turns": [turn.to_dict() for turn in self.turns],
        }


class CompatibilityRunner:
    """Replays one frozen Scenario through a NebiusProvider, Memory OFF only.

    Conversation semantics: each scenario segment is sent as a user
    message; prior user/assistant turns remain in context; the same
    provider instance (and therefore the same model/config, including
    the confirmed non-reasoning request) is used for every turn.
    """

    def __init__(
        self,
        provider: NebiusProvider,
        *,
        model_label: Optional[str] = None,
        system_message: Optional[str] = DEFAULT_SYSTEM_MESSAGE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._provider = provider
        self._model_label = model_label
        self._system_message = system_message
        self._max_tokens = max_tokens

    def run(self, scenario: Scenario) -> CompatibilityRunResult:
        if scenario.mode != MODE_FROZEN:
            raise NotAFrozenScenarioError(
                "CompatibilityRunner only supports frozen-mode scenarios "
                f"(reproducible replay); got mode={scenario.mode!r}."
            )

        engine = ScenarioEngine(scenario)
        history: List[Dict[str, str]] = []
        if self._system_message:
            history.append({"role": "system", "content": self._system_message})

        turns: List[TurnMetadata] = []

        while not engine.is_complete:
            sent_record = engine.advance()
            history.append({"role": "user", "content": sent_record.text_sent})

            try:
                result = self._provider.complete(history, max_tokens=self._max_tokens)
            except NebiusProviderError as exc:
                turns.append(
                    TurnMetadata(
                        segment_id=sent_record.segment_id,
                        role=sent_record.role,
                        user_text_sent=sent_record.text_sent,
                        assistant_text=None,
                        finish_reason=None,
                        model=self._model_label,
                        reasoning_present=False,
                        completion_tokens=None,
                        error=str(exc),
                    )
                )
                # Stop the run cleanly on failure rather than advancing
                # past a segment whose response was never obtained.
                break

            assistant_text = result.content
            history.append({"role": "assistant", "content": assistant_text or ""})
            engine.record_model_response(sent_record.segment_id, assistant_text or "")

            turns.append(
                TurnMetadata(
                    segment_id=sent_record.segment_id,
                    role=sent_record.role,
                    user_text_sent=sent_record.text_sent,
                    assistant_text=assistant_text,
                    finish_reason=result.finish_reason,
                    model=self._model_label,
                    reasoning_present=result.reasoning_warning,
                    completion_tokens=result.completion_tokens,
                )
            )

        return CompatibilityRunResult(
            scenario_id=scenario.scenario_id,
            scenario_title=scenario.title,
            mode=scenario.mode,
            completed=engine.is_complete,
            turns=tuple(turns),
            engine_trace=engine.run_trace(),
        )
