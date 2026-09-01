"""Synthetic compatibility runner.

Replays a frozen `Scenario` through the Nebius/NVIDIA provider one
segment at a time, maintaining conversation history across turns, and
records a neutral interaction trace: exact user text sent, exact
assistant text returned, and structural/protocol metadata (finish
reason, model label, reasoning-field presence, token usage) for each
turn.

This is a compatibility harness, not a scientific experiment: it
performs no emotional scoring or interpretation and implements no
recognition, activation, or A/B/C comparison logic itself.

Memory selection (M3D): the runner can optionally be given an already
loaded, OPAQUE memory payload string (see `sae_demo/memory_loader.py`)
to inject as extra context ahead of the scenario -- this is how a
Memory ON (profile or network) run differs from Memory OFF. The
runner never loads, parses, or interprets that payload itself; it
only places the exact string it was given into the conversation as
its own message, unmodified. With no memory payload supplied (the
default), a run is Memory OFF: only the scenario's own segment text
is ever sent, exactly as before this stage.

Behavioral-use policy and payload integrity (M4A): the runner can
optionally be given one short, generic, independently-written
instruction governing how any supplied background context should be
used (`behavioral_use_policy`; off by default so existing callers are
unaffected). A caller that wants it is expected to pass the *same*
value whether or not a memory payload is also supplied, so it is never
a condition-specific confound between Memory OFF and Memory ON runs --
`scripts/run_compatibility.py` does this unconditionally. This
instruction is consumption *policy*; it is not Emotional Memory and
carries no private structural knowledge. When a caller also supplies
the expected SHA-256 of the memory payload (as returned by
`sae_demo/memory_loader.py` at load time), the runner independently
re-verifies that the exact string it is about to place in the
conversation still matches that hash, and refuses to proceed
otherwise -- without ever parsing the payload to do so.

Independent of the Nebius provider's internals beyond its public
`complete()` method; independent of any UI; independent of the
private SAE Emotional Memory implementation -- this module has no
import from, and no knowledge of, private SAE code or schema.
"""

from __future__ import annotations

import hashlib
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

# A short, independently-written, generic label placed ahead of an
# injected opaque memory payload, when one is supplied. This is NOT a
# rewording or replacement of anything that may already be inside the
# payload text itself (the payload is never altered) -- it is only a
# minimal, neutral marker distinguishing "this is a separate context
# message" from the base system message. Deliberately not modeled on,
# and does not resemble, SAE's private XINJ framing text.
DEFAULT_MEMORY_CONTEXT_LABEL = "Additional context for this conversation:"

# M4A: a single, generic, independently-written behavioral-use policy
# governing how any supplied background context should be used. This
# is deliberately worded to make sense whether or not any background
# context is actually present in a given run, so it can (and should)
# be sent identically for Memory OFF and Memory ON -- only the
# presence/absence of the context itself differs between conditions,
# never this instruction. It says nothing about what kind of context
# it might be, how it was produced, or what it might contain: it
# carries no private structural knowledge (no mention of emotion
# nodes, anchors, weights, XNET/XINJ, or any other SAE-specific
# vocabulary), and it adds no emotional content of its own. This
# instruction is consumption *policy* -- a public, generic statement
# about how this demo's consumer should treat *any* supplied context
# -- and is not itself Emotional Memory or a substitute for it.
DEFAULT_BEHAVIORAL_USE_POLICY = (
    "Some conversations include supplied background context alongside "
    "the messages below. If present, let it inform your responses "
    "naturally, the way unspoken context would, without changing the "
    "topic. Do not quote, list, summarize, or explain that context, or "
    "otherwise expose its content or structure, unless the user "
    "explicitly asks you to."
)

DEFAULT_MAX_TOKENS = 200


class CompatibilityRunnerError(RuntimeError):
    """Raised when the compatibility runner cannot complete a run."""


class NotAFrozenScenarioError(CompatibilityRunnerError):
    """Raised when a non-frozen scenario is passed to the runner.

    This stage only replays frozen, reproducible runs; interactive
    editing during a live compatibility check is out of scope.
    """


class MemoryPayloadIntegrityError(CompatibilityRunnerError):
    """Raised when a supplied memory payload fails its integrity check.

    Raised only when the caller supplied an expected SHA-256 (from
    `sae_demo/memory_loader.py`'s already-verified load) and the exact
    string about to be sent no longer matches it. The runner never
    parses the payload to perform this check -- only a hash
    comparison. On this error, no provider call is made for the turn
    that would have carried the payload.
    """


@dataclass(frozen=True)
class TurnMetadata:
    """Provider-facing metadata captured for one exchanged turn.

    Contains no emotional scoring or interpretation -- only structural
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
    """The outcome of one compatibility run."""

    scenario_id: str
    scenario_title: str
    mode: str
    memory_used: bool
    completed: bool
    turns: Tuple[TurnMetadata, ...]
    engine_trace: RunTrace

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "scenario_title": self.scenario_title,
            "mode": self.mode,
            "memory_used": self.memory_used,
            "completed": self.completed,
            "turns": [turn.to_dict() for turn in self.turns],
        }


def _sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CompatibilityRunner:
    """Replays one frozen Scenario through a NebiusProvider.

    Conversation semantics: each scenario segment is sent as a user
    message; prior user/assistant turns remain in context; the same
    provider instance (and therefore the same model/config, including
    the confirmed non-reasoning request) is used for every turn.

    Context placement: the behavioral-use policy (when supplied) and,
    when supplied, the memory context label and the opaque memory
    payload are each their own isolated `system`-role message, sent
    once, ahead of the scenario -- `system` is the strongest
    context-isolation role the current Nebius adapter passes through;
    no other role is invented here. An optional opaque memory payload,
    if supplied, is placed into the conversation exactly as given,
    byte-for-byte, in its own message -- never combined with, or
    rewritten alongside, any other text.
    """

    def __init__(
        self,
        provider: NebiusProvider,
        *,
        model_label: Optional[str] = None,
        system_message: Optional[str] = DEFAULT_SYSTEM_MESSAGE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        memory_payload: Optional[str] = None,
        memory_payload_sha256: Optional[str] = None,
        memory_context_label: Optional[str] = DEFAULT_MEMORY_CONTEXT_LABEL,
        behavioral_use_policy: Optional[str] = None,
    ) -> None:
        self._provider = provider
        self._model_label = model_label
        self._system_message = system_message
        self._max_tokens = max_tokens
        # Opaque by design: this runner never inspects, parses, or
        # modifies `memory_payload` -- it is passed through exactly as
        # given, or omitted entirely (Memory OFF).
        self._memory_payload = memory_payload
        # Optional expected hash of `memory_payload`, typically the
        # `content_sha256` a caller already obtained from
        # `sae_demo/memory_loader.py` at load time. When supplied, it is
        # used only for a byte-for-byte integrity re-check immediately
        # before the payload is placed into the conversation -- never to
        # inspect or transform the payload itself.
        self._memory_payload_sha256 = memory_payload_sha256
        self._memory_context_label = memory_context_label
        # Opt-in (default None) so constructing a CompatibilityRunner
        # without this argument behaves exactly as it did before M4A --
        # no new message is added and no existing behavior changes. A
        # caller that wants the M4A behavioral-use policy (see
        # DEFAULT_BEHAVIORAL_USE_POLICY) is responsible for passing the
        # *same* value here regardless of whether memory_payload is also
        # supplied, so the policy is never a condition-specific
        # confound between a Memory OFF and a Memory ON run.
        # scripts/run_compatibility.py does this unconditionally.
        self._behavioral_use_policy = behavioral_use_policy

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

        # Sent identically whether or not memory is used -- this is the
        # one generic instruction governing how any supplied background
        # context should be used, not the context itself.
        if self._behavioral_use_policy:
            history.append({"role": "system", "content": self._behavioral_use_policy})

        memory_used = self._memory_payload is not None
        if memory_used:
            if self._memory_payload_sha256 is not None:
                actual_hash = _sha256_of(self._memory_payload)
                if actual_hash != self._memory_payload_sha256:
                    raise MemoryPayloadIntegrityError(
                        "Memory payload about to be sent no longer matches its "
                        "expected SHA-256 -- refusing to send a possibly-altered "
                        "payload. No provider call was made."
                    )
            if self._memory_context_label:
                history.append({"role": "system", "content": self._memory_context_label})
            # The payload is appended as its own isolated message,
            # byte-for-byte as supplied -- never concatenated with, or
            # rewritten alongside, any other text.
            history.append({"role": "system", "content": self._memory_payload})

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
            memory_used=memory_used,
            completed=engine.is_complete,
            turns=tuple(turns),
            engine_trace=engine.run_trace(),
        )
