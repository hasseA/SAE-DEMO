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

Behavioral-use policy and payload integrity (M4A, extended M4B): the
runner can optionally be given one short, generic, independently-
written instruction governing how any supplied background context
should be used (`behavioral_use_policy`; off by default so existing
callers are unaffected). A caller that wants it is expected to pass
the *same* value whether or not a memory payload is also supplied, so
it is never a condition-specific confound between Memory OFF and
Memory ON runs -- `scripts/run_compatibility.py` does this
unconditionally. This instruction is consumption *policy*; it is not
Emotional Memory and carries no private structural knowledge. M4B
extends its text (only its text -- no placement, parameter, or
signature change) with one additional, generic rule: concrete
narrative details in a response (people, places, events, objects,
remembered scenes) should stay grounded in what the user has actually
provided in the current conversation, not be invented from background
context, unless the user explicitly asks about that background
context. Background context influencing interpretation, tone, or
emotional/relational stance remains explicitly allowed -- this is a
grounding constraint on invented concrete narrative facts, not a
restriction on emotional engagement. When a caller also supplies the
expected SHA-256 of the memory payload (as returned by
`sae_demo/memory_loader.py` at load time), the runner independently
re-verifies that the exact string it is about to place in the
conversation still matches that hash, and refuses to proceed
otherwise -- without ever parsing the payload to do so.

Independent of the Nebius provider's internals beyond its public
`complete()` method; independent of any UI; independent of the
private SAE Emotional Memory implementation -- this module has no
import from, and no knowledge of, private SAE code or schema.

Incremental use (M5C): `run()` replays an entire scenario in one call,
which does not fit a web UI that advances one segment at a time. Its
memory-placement/behavioral-policy logic is factored into two public
methods, `build_history()` and `send_turn()`, which `run()` itself now
calls internally. A caller that needs step-by-step control (e.g. the
web app's scenario-run flow in `sae_demo/web_app.py`) calls
`build_history()` once and `send_turn()` once per segment instead of
`run()`, sharing this exact same implementation rather than
reimplementing memory placement or behavioral-policy ordering
separately -- there is intentionally only one implementation of that
logic in this project.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

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

# M4A, extended M4B: a single, generic, independently-written
# behavioral-use policy governing how any supplied background context
# should be used. This is deliberately worded to make sense whether or
# not any background context is actually present in a given run, so it
# can (and should) be sent identically for Memory OFF and Memory ON --
# only the presence/absence of the context itself differs between
# conditions, never this instruction. It says nothing about what kind
# of context it might be, how it was produced, or what it might
# contain: it carries no private structural knowledge (no mention of
# emotion nodes, anchors, weights, XNET/XINJ, or any other SAE-specific
# vocabulary), and it adds no emotional content of its own. This
# instruction is consumption *policy* -- a public, generic statement
# about how this demo's consumer should treat *any* supplied context
# -- and is not itself Emotional Memory or a substitute for it.
#
# M4B adds one thing to the M4A text: a scenario-grounding rule. M3D's
# private compatibility testing showed that, after M4A's anti-
# recitation rule reduced explicit representation recitation (numeric
# weights, "emotional map" language, representation-like tables), the
# model could still introduce concrete narrative details -- people,
# places, events, objects, remembered scenes -- that trace to
# background context rather than to anything in the current
# conversation. The distinction this rule preserves: background
# context (state) may influence interpretation, salience, tone, and
# relational/emotional stance; it should not supply invented concrete
# narrative facts presented as though they came from the current
# conversation. This rule does not restrict emotional interpretation
# or relational behavior -- only invented, unprompted concrete detail.
DEFAULT_BEHAVIORAL_USE_POLICY = (
    "Some conversations include supplied background context alongside "
    "the messages below. If present, let it inform your responses "
    "naturally, the way unspoken context would, without changing the "
    "topic. Do not quote, list, summarize, or explain that context, or "
    "otherwise expose its content or structure, unless the user "
    "explicitly asks you to. Keep concrete details in your response -- "
    "people, places, events, objects, and remembered scenes -- grounded "
    "in what the user has actually provided in this conversation. "
    "Background context may still shape your interpretation, tone, and "
    "emotional or relational stance, but should not introduce concrete "
    "details of its own unless the user explicitly asks about it."
)

DEFAULT_MAX_TOKENS = 400

# M5G: configurable via environment, so the completion-token budget is
# one operator-tunable value instead of a constant hard-coded in
# multiple places. `resolve_max_tokens()` is the single place this
# value is ever read at request time; `sae_demo/web_app.py` calls it
# once per run construction (`_start_run_entry`) and passes the exact
# same result to both a Memory OFF run and a Memory ON run -- there is
# no code path that gives one condition a different budget than the
# other, which is the controlling invariant recorded in
# `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md` (Section
# 7: `max_tokens` held identical between conditions). Changing this
# value changes both conditions' budget together, never one alone.
#
# M5G raised the default from 200 to 400. Rationale: 200 completion
# tokens (roughly 130-150 English words) repeatedly proved too small
# for a natural multi-sentence reflective reply to a scenario segment,
# causing live Nemotron responses to end mid-sentence -- a display/
# readability problem, not a scientific one, but one that undermines a
# hackathon demo's first impression. Doubling the budget is the
# smallest change that gives a completion realistic room to reach a
# sentence boundary without materially changing latency/cost or
# altering anything about scenario content, memory placement, or the
# behavioral-use policy. This is a token-budget tuning decision only;
# it does not touch model choice, reasoning configuration, or any
# scenario/memory content.
MAX_TOKENS_ENV_VAR = "SAE_DEMO_MAX_TOKENS"

# Defensive bounds for an operator-supplied override: large enough to
# comfortably fit a multi-sentence reply, small enough to keep a demo
# run's latency/cost sane. An override outside this range, or one that
# isn't a valid integer, is ignored in favor of `DEFAULT_MAX_TOKENS`
# rather than silently sent to the provider as-is or allowed to break a
# run with a confusing provider-side error.
_MIN_MAX_TOKENS = 50
_MAX_MAX_TOKENS = 2000


def resolve_max_tokens(env: Optional[Mapping[str, str]] = None) -> int:
    """Resolve the completion-token budget for one provider call.

    Defaults to `DEFAULT_MAX_TOKENS`; overridable via the
    `SAE_DEMO_MAX_TOKENS` environment variable (or an injectable `env`
    mapping, for testing), following the same pattern as
    `sae_demo/runtime_paths.py`'s `local_root()`. An override that
    isn't a valid positive integer, or falls outside
    [`_MIN_MAX_TOKENS`, `_MAX_MAX_TOKENS`], is ignored -- this function
    never raises and never sends a nonsensical value to the provider;
    it silently falls back to the default instead.

    Deliberately stateless and side-effect-free so every caller within
    one process resolves the exact same value from the exact same
    environment -- this is what keeps Memory OFF and Memory ON calls
    using an identical budget.
    """

    source = env if env is not None else os.environ
    raw = source.get(MAX_TOKENS_ENV_VAR)
    if not raw:
        return DEFAULT_MAX_TOKENS

    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_TOKENS

    if value < _MIN_MAX_TOKENS or value > _MAX_MAX_TOKENS:
        return DEFAULT_MAX_TOKENS

    return value


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
        # caller that wants the M4A/M4B behavioral-use policy (see
        # DEFAULT_BEHAVIORAL_USE_POLICY) is responsible for passing the
        # *same* value here regardless of whether memory_payload is also
        # supplied, so the policy is never a condition-specific
        # confound between a Memory OFF and a Memory ON run.
        # scripts/run_compatibility.py does this unconditionally.
        self._behavioral_use_policy = behavioral_use_policy

    def build_history(self) -> Tuple[List[Dict[str, str]], bool]:
        """Build the fixed, pre-scenario conversation history for one run.

        This is the *only* place memory placement/policy ordering is
        implemented: system message, then the behavioral-use policy
        (sent identically regardless of memory), then -- only when a
        memory payload is supplied -- an independent hash re-check,
        the memory context label, and the opaque payload itself,
        each its own isolated ``system``-role message. Both `run` and
        any incremental caller (e.g. a step-by-step web run) share this
        one implementation so memory/policy semantics cannot drift
        between an all-at-once and a one-segment-at-a-time execution
        path.

        Returns ``(history, memory_used)``. Raises
        `MemoryPayloadIntegrityError` (no provider call made) if a
        supplied expected hash no longer matches the payload.
        """

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

        return history, memory_used

    def send_turn(
        self,
        history: List[Dict[str, str]],
        segment_id: str,
        role: str,
        user_text: str,
    ) -> TurnMetadata:
        """Send one already-obtained segment's text and record the turn.

        Mutates `history` in place (appends the user message, and, on
        success, the assistant message) so a caller driving a run one
        segment at a time can keep reusing the same accumulated
        history object across calls -- this is the same accumulation
        behavior `run` itself relies on internally.
        """

        history.append({"role": "user", "content": user_text})

        try:
            result = self._provider.complete(history, max_tokens=self._max_tokens)
        except NebiusProviderError as exc:
            return TurnMetadata(
                segment_id=segment_id,
                role=role,
                user_text_sent=user_text,
                assistant_text=None,
                finish_reason=None,
                model=self._model_label,
                reasoning_present=False,
                completion_tokens=None,
                error=str(exc),
            )

        assistant_text = result.content
        history.append({"role": "assistant", "content": assistant_text or ""})

        return TurnMetadata(
            segment_id=segment_id,
            role=role,
            user_text_sent=user_text,
            assistant_text=assistant_text,
            finish_reason=result.finish_reason,
            model=self._model_label,
            reasoning_present=result.reasoning_warning,
            completion_tokens=result.completion_tokens,
        )

    def run(self, scenario: Scenario) -> CompatibilityRunResult:
        if scenario.mode != MODE_FROZEN:
            raise NotAFrozenScenarioError(
                "CompatibilityRunner only supports frozen-mode scenarios "
                f"(reproducible replay); got mode={scenario.mode!r}."
            )

        engine = ScenarioEngine(scenario)
        history, memory_used = self.build_history()

        turns: List[TurnMetadata] = []

        while not engine.is_complete:
            sent_record = engine.advance()
            turn = self.send_turn(
                history, sent_record.segment_id, sent_record.role, sent_record.text_sent
            )
            turns.append(turn)

            if turn.error is not None:
                # Stop the run cleanly on failure rather than advancing
                # past a segment whose response was never obtained.
                break

            engine.record_model_response(sent_record.segment_id, turn.assistant_text or "")

        return CompatibilityRunResult(
            scenario_id=scenario.scenario_id,
            scenario_title=scenario.title,
            mode=scenario.mode,
            memory_used=memory_used,
            completed=engine.is_complete,
            turns=tuple(turns),
            engine_trace=engine.run_trace(),
        )
