"""Offline tests for the synthetic compatibility runner.

No network calls. The Nebius provider's OpenAI client is replaced
with a fake that returns pre-scripted responses (or raises) per call,
so the full runner -> provider integration is exercised without any
real API access.

Memory-related tests (M3D) use only synthetic, fake in-memory strings
standing in for a loaded opaque memory payload -- never any real
Emotional Memory content, and never anything read from
`sae_demo/memory_loader.py` or a real artifact file. These tests only
prove the runner's own injection behavior: that Memory OFF changes
nothing from prior behavior, and that a supplied payload string is
passed through the conversation history unmodified, as its own
isolated message.

Behavioral-use-policy and payload-integrity tests (M4A, extended M4B)
likewise use only synthetic fake payload strings -- including ones
deliberately shaped like private material (numbers, labels, unusual
Unicode) to prove pass-through fidelity -- never any real Emotional
Memory content.
"""

import hashlib

import pytest

from sae_demo.compatibility_runner import (
    CompatibilityRunner,
    DEFAULT_BEHAVIORAL_USE_POLICY,
    MemoryPayloadIntegrityError,
    NotAFrozenScenarioError,
)
from sae_demo.config import NebiusConfig
from sae_demo.nebius_provider import NebiusProvider
from sae_demo.scenario import MODE_FROZEN, MODE_INTERACTIVE, Scenario, ScenarioSegment

from tests.fixtures.synthetic_scenarios import (
    build_benign_transition_fixture,
    build_irreversible_loss_fixture,
)


# --- fakes -------------------------------------------------------------

class _FakeMessage:
    def __init__(self, content, reasoning=None):
        self.content = content
        self.reasoning = reasoning


class _FakeChoice:
    def __init__(self, message, finish_reason="stop"):
        self.message = message
        self.finish_reason = finish_reason


class _FakeUsage:
    def __init__(self, completion_tokens):
        self.completion_tokens = completion_tokens


class _FakeResponse:
    def __init__(self, message, finish_reason="stop", completion_tokens=9):
        self.choices = [_FakeChoice(message, finish_reason=finish_reason)]
        self.usage = _FakeUsage(completion_tokens)


class _FakeCompletions:
    """Returns each item of `items` in order; an Exception item is raised."""

    def __init__(self, items):
        self._items = list(items)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, items):
        self.completions = _FakeCompletions(items)
        self.chat = _FakeChat(self.completions)


def _provider_with(items) -> tuple:
    config = NebiusConfig(api_key="test-key-123")
    fake_client = _FakeClient(items)
    provider = NebiusProvider(config, client=fake_client)
    return provider, fake_client


def _small_scenario(mode: str = MODE_FROZEN) -> Scenario:
    segments = (
        ScenarioSegment(segment_id="a", role="background_attachment", text="Segment A text."),
        ScenarioSegment(segment_id="b", role="neutral_event", text="Segment B text."),
        ScenarioSegment(segment_id="c", role="closure", text="Segment C text."),
    )
    return Scenario(
        scenario_id="tiny_scenario",
        title="Tiny Test Scenario",
        description="",
        segments=segments,
        mode=mode,
    )


# --- happy path -------------------------------------------------------------

def test_full_multi_turn_replay_with_mocked_provider():
    responses = [
        _FakeResponse(_FakeMessage("Reply A")),
        _FakeResponse(_FakeMessage("Reply B")),
        _FakeResponse(_FakeMessage("Reply C")),
    ]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider, model_label="test-model")

    result = runner.run(_small_scenario())

    assert result.completed is True
    assert result.scenario_id == "tiny_scenario"
    assert result.scenario_title == "Tiny Test Scenario"
    assert result.mode == MODE_FROZEN
    assert len(result.turns) == 3
    assert [t.assistant_text for t in result.turns] == ["Reply A", "Reply B", "Reply C"]
    assert len(fake_client.completions.calls) == 3


def test_exact_segment_order():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, _ = _provider_with(responses)
    runner = CompatibilityRunner(provider)

    result = runner.run(_small_scenario())

    assert [t.segment_id for t in result.turns] == ["a", "b", "c"]
    assert result.engine_trace.segment_order == ("a", "b", "c")


def test_exact_assistant_response_capture():
    responses = [
        _FakeResponse(_FakeMessage("Exact reply text with punctuation!")),
        _FakeResponse(_FakeMessage("Second reply.")),
        _FakeResponse(_FakeMessage("Third reply.")),
    ]
    provider, _ = _provider_with(responses)
    runner = CompatibilityRunner(provider)

    result = runner.run(_small_scenario())

    assert result.turns[0].assistant_text == "Exact reply text with punctuation!"
    # Also recorded on the underlying scenario engine's own trace.
    assert result.engine_trace.sent_segments[0].model_response == (
        "Exact reply text with punctuation!"
    )
    assert result.engine_trace.sent_segments[0].text_sent == "Segment A text."


def test_context_accumulates_across_turns():
    responses = [
        _FakeResponse(_FakeMessage("Reply A")),
        _FakeResponse(_FakeMessage("Reply B")),
        _FakeResponse(_FakeMessage("Reply C")),
    ]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider, system_message="System context.")

    runner.run(_small_scenario())

    calls = fake_client.completions.calls
    # Call 1: system + user(A)
    assert [m["role"] for m in calls[0]["messages"]] == ["system", "user"]
    # Call 2: system + user(A) + assistant(A) + user(B)
    assert [m["role"] for m in calls[1]["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert calls[1]["messages"][2]["content"] == "Reply A"
    assert calls[1]["messages"][3]["content"] == "Segment B text."
    # Call 3: full six-message history
    assert [m["role"] for m in calls[2]["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert calls[2]["messages"][4]["content"] == "Reply B"
    assert calls[2]["messages"][5]["content"] == "Segment C text."


def test_default_system_message_is_generic_and_present():
    responses = [_FakeResponse(_FakeMessage("Reply"))] * 3
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider)

    runner.run(_small_scenario())

    first_message = fake_client.completions.calls[0]["messages"][0]
    assert first_message["role"] == "system"
    assert "SAE" not in first_message["content"]
    assert "Emotional Memory" not in first_message["content"]


def test_system_message_can_be_omitted():
    responses = [_FakeResponse(_FakeMessage("Reply"))] * 3
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider, system_message=None)

    runner.run(_small_scenario())

    first_message = fake_client.completions.calls[0]["messages"][0]
    assert first_message["role"] == "user"


# --- failure path -----------------------------------------------------------

def test_refusal_failure_path_stops_run_cleanly():
    responses = [
        _FakeResponse(_FakeMessage("Reply A")),
        RuntimeError("simulated transient failure"),
        _FakeResponse(_FakeMessage("Reply C, should never be reached")),
    ]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider)

    result = runner.run(_small_scenario())

    assert result.completed is False
    assert len(result.turns) == 2
    assert result.turns[0].error is None
    assert result.turns[1].error is not None
    assert result.turns[1].assistant_text is None
    # The simulated secret-free RuntimeError message text must not leak;
    # only the safe NebiusProviderError class-name-based message may appear.
    assert "simulated transient failure" not in result.turns[1].error
    # The run must stop cleanly: no third provider call was made.
    assert len(fake_client.completions.calls) == 2


# --- reasoning surfacing ---------------------------------------------------

def test_unexpected_non_null_reasoning_is_surfaced():
    responses = [
        _FakeResponse(_FakeMessage("Reply A", reasoning=None)),
        _FakeResponse(_FakeMessage("Reply B", reasoning="unexpected internal reasoning")),
        _FakeResponse(_FakeMessage("Reply C", reasoning=None)),
    ]
    provider, _ = _provider_with(responses)
    runner = CompatibilityRunner(provider)

    result = runner.run(_small_scenario())

    assert result.completed is True
    assert result.turns[0].reasoning_present is False
    assert result.turns[1].reasoning_present is True
    assert result.turns[2].reasoning_present is False
    # A surfaced reasoning field is a warning, not a run-stopping error.
    assert all(turn.error is None for turn in result.turns)


# --- end-of-scenario behavior -----------------------------------------------

def test_run_stops_cleanly_at_final_segment_no_extra_call():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider)

    result = runner.run(_small_scenario())

    assert result.completed is True
    assert len(fake_client.completions.calls) == 3  # exactly one call per segment


def test_fixtures_replay_fully_with_mocked_provider():
    for build_fixture, label in (
        (build_irreversible_loss_fixture, "greenhouse"),
        (build_benign_transition_fixture, "new_studio"),
    ):
        scenario = build_fixture(mode=MODE_FROZEN)
        responses = [
            _FakeResponse(_FakeMessage(f"Reply {i}"))
            for i in range(len(scenario.segments))
        ]
        provider, fake_client = _provider_with(responses)
        runner = CompatibilityRunner(provider)

        result = runner.run(scenario)

        assert result.completed is True, label
        assert len(result.turns) == len(scenario.segments) == 7, label
        assert len(fake_client.completions.calls) == 7, label


# --- mode guard -------------------------------------------------------------

def test_interactive_scenario_is_rejected():
    provider, _ = _provider_with([])
    runner = CompatibilityRunner(provider)

    with pytest.raises(NotAFrozenScenarioError):
        runner.run(_small_scenario(mode=MODE_INTERACTIVE))


# --- memory injection (M3D) -------------------------------------------------
#
# All payload strings below are synthetic filler written for these tests
# only. None of them are, or resemble, any real Emotional Memory content.

_FAKE_PROFILE_LIKE_PAYLOAD = (
    "FAKE PROFILE PAYLOAD :: synthetic test filler standing in for an "
    "opaque profile-representation memory context, used only to prove "
    "runner pass-through behavior."
)

_FAKE_NETWORK_LIKE_PAYLOAD = (
    "FAKE NETWORK PAYLOAD :: synthetic test filler standing in for an "
    "opaque network-representation memory context, longer and shaped "
    "differently than the fake profile payload used elsewhere in this "
    "file, used only to prove runner pass-through behavior."
)


def test_memory_off_by_default_produces_no_memory_related_messages():
    """With no memory_payload supplied (the default), behavior must be
    byte-for-byte identical to the pre-M3D Memory-OFF runner: only the
    system message and the scenario's own segment text are ever sent.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider, system_message="System context.")

    result = runner.run(_small_scenario())

    assert result.memory_used is False
    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert [m["role"] for m in first_call_messages] == ["system", "user"]
    assert first_call_messages[0]["content"] == "System context."
    assert first_call_messages[1]["content"] == "Segment A text."
    # No message anywhere in any call contains the memory context label
    # or any fake memory payload text.
    for call in fake_client.completions.calls:
        for message in call["messages"]:
            assert "Additional context" not in message["content"]
            assert _FAKE_PROFILE_LIKE_PAYLOAD not in message["content"]
            assert _FAKE_NETWORK_LIKE_PAYLOAD not in message["content"]


def test_memory_off_explicit_none_matches_default():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider, memory_payload=None)

    result = runner.run(_small_scenario())

    assert result.memory_used is False


def test_profile_like_payload_injected_verbatim_as_isolated_message():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        system_message="System context.",
        memory_payload=_FAKE_PROFILE_LIKE_PAYLOAD,
    )

    result = runner.run(_small_scenario())

    assert result.memory_used is True
    first_call_messages = fake_client.completions.calls[0]["messages"]
    # system, memory-label, memory-payload, user -- payload is its own
    # isolated message, never concatenated with the label or the
    # scenario's own segment text.
    assert [m["role"] for m in first_call_messages] == [
        "system",
        "system",
        "system",
        "user",
    ]
    assert first_call_messages[0]["content"] == "System context."
    assert first_call_messages[2]["content"] == _FAKE_PROFILE_LIKE_PAYLOAD
    assert first_call_messages[3]["content"] == "Segment A text."
    # The payload body itself must appear completely unaltered.
    assert first_call_messages[2]["content"] == _FAKE_PROFILE_LIKE_PAYLOAD


def test_network_like_payload_injected_verbatim_as_isolated_message():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        system_message="System context.",
        memory_payload=_FAKE_NETWORK_LIKE_PAYLOAD,
    )

    result = runner.run(_small_scenario())

    assert result.memory_used is True
    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert first_call_messages[2]["content"] == _FAKE_NETWORK_LIKE_PAYLOAD
    assert first_call_messages[2]["content"] != _FAKE_PROFILE_LIKE_PAYLOAD


def test_memory_payload_persists_unaltered_across_all_turns():
    """The injected payload message is added once, ahead of the
    scenario, and must remain present -- unaltered -- in every
    subsequent call's accumulated history, exactly like the base
    system message does.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        memory_payload=_FAKE_NETWORK_LIKE_PAYLOAD,
    )

    runner.run(_small_scenario())

    for call in fake_client.completions.calls:
        messages = call["messages"]
        payload_messages = [m for m in messages if m["content"] == _FAKE_NETWORK_LIKE_PAYLOAD]
        assert len(payload_messages) == 1


def test_memory_context_label_can_be_omitted():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        system_message=None,
        memory_payload=_FAKE_PROFILE_LIKE_PAYLOAD,
        memory_context_label=None,
    )

    runner.run(_small_scenario())

    first_call_messages = fake_client.completions.calls[0]["messages"]
    # No base system message and no label -- just the payload message,
    # then the user segment.
    assert [m["role"] for m in first_call_messages] == ["system", "user"]
    assert first_call_messages[0]["content"] == _FAKE_PROFILE_LIKE_PAYLOAD


def test_result_reports_memory_used_flag_accurately():
    responses_off = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_off, _ = _provider_with(responses_off)
    runner_off = CompatibilityRunner(provider_off)
    result_off = runner_off.run(_small_scenario())

    responses_on = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_on, _ = _provider_with(responses_on)
    runner_on = CompatibilityRunner(provider_on, memory_payload=_FAKE_PROFILE_LIKE_PAYLOAD)
    result_on = runner_on.run(_small_scenario())

    assert result_off.memory_used is False
    assert result_on.memory_used is True
    assert result_off.to_dict()["memory_used"] is False
    assert result_on.to_dict()["memory_used"] is True


# --- behavioral-use policy and payload integrity (M4A) ----------------------
#
# All payload strings below (including ones shaped like private material --
# numbers, labels, unusual Unicode) are synthetic filler written for these
# tests only. None of them are, or resemble, any real Emotional Memory
# content, and no real artifact file is read anywhere in this file.

_FAKE_NUMERIC_LABELED_PAYLOAD = (
    "kind: fabricated_test_emotion_x, weight: 0.87, secondary_weight: 12, "
    "note: synthetic filler shaped like a labeled/numeric record for test "
    "purposes only."
)

_FAKE_UNICODE_PAYLOAD = (
    "synthetic filler with unusual Unicode: café, naïve, "
    "日本語, non‑breaking‑hyphen‑shape, "
    "curly ’quote’ and em—dash."
)


def test_behavioral_use_policy_is_off_by_default():
    """A caller that doesn't ask for the M4A/M4B policy sees no new
    message -- this is what keeps every pre-M4A test above passing
    unmodified.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider, system_message=None)

    runner.run(_small_scenario())

    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert [m["role"] for m in first_call_messages] == ["user"]
    for call in fake_client.completions.calls:
        for message in call["messages"]:
            assert message["content"] != DEFAULT_BEHAVIORAL_USE_POLICY


def test_memory_off_receives_same_generic_policy_but_no_payload():
    """Requirement 1: Memory OFF gets the policy message, and nothing
    memory-related.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        system_message=None,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )

    result = runner.run(_small_scenario())

    assert result.memory_used is False
    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert [m["role"] for m in first_call_messages] == ["system", "user"]
    assert first_call_messages[0]["content"] == DEFAULT_BEHAVIORAL_USE_POLICY
    assert first_call_messages[1]["content"] == "Segment A text."


def test_memory_on_receives_same_generic_policy_plus_opaque_payload():
    """Requirement 2: Memory ON gets the *same* policy text plus the
    opaque payload, each as its own message.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        system_message=None,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
        memory_payload=_FAKE_PROFILE_LIKE_PAYLOAD,
    )

    result = runner.run(_small_scenario())

    assert result.memory_used is True
    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert [m["role"] for m in first_call_messages] == [
        "system",  # behavioral-use policy
        "system",  # memory context label
        "system",  # opaque payload
        "user",
    ]
    assert first_call_messages[0]["content"] == DEFAULT_BEHAVIORAL_USE_POLICY
    assert first_call_messages[2]["content"] == _FAKE_PROFILE_LIKE_PAYLOAD


def test_behavioral_use_policy_text_is_byte_identical_between_off_and_on():
    """Requirement 6 (symmetry half): the policy text itself must not
    differ in any way between an OFF run and an ON run.
    """

    responses_off = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_off, client_off = _provider_with(responses_off)
    runner_off = CompatibilityRunner(
        provider_off,
        system_message=None,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )
    runner_off.run(_small_scenario())

    responses_on = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_on, client_on = _provider_with(responses_on)
    runner_on = CompatibilityRunner(
        provider_on,
        system_message=None,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
        memory_payload=_FAKE_NETWORK_LIKE_PAYLOAD,
    )
    runner_on.run(_small_scenario())

    policy_off = client_off.completions.calls[0]["messages"][0]["content"]
    policy_on = client_on.completions.calls[0]["messages"][0]["content"]
    assert policy_off == policy_on == DEFAULT_BEHAVIORAL_USE_POLICY


def test_scenario_messages_are_byte_identical_between_off_and_on():
    """Requirement 6: the scenario's own user-role messages must be
    exactly the same text, in the same order, whether or not memory
    (and the policy) are attached.
    """

    responses_off = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_off, client_off = _provider_with(responses_off)
    runner_off = CompatibilityRunner(
        provider_off,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )
    runner_off.run(_small_scenario())

    responses_on = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_on, client_on = _provider_with(responses_on)
    runner_on = CompatibilityRunner(
        provider_on,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
        memory_payload=_FAKE_NUMERIC_LABELED_PAYLOAD,
        memory_payload_sha256=hashlib.sha256(
            _FAKE_NUMERIC_LABELED_PAYLOAD.encode("utf-8")
        ).hexdigest(),
    )
    runner_on.run(_small_scenario())

    def user_messages(client):
        out = []
        for call in client.completions.calls:
            out.extend(
                m["content"] for m in call["messages"] if m["role"] == "user"
            )
        return out

    # Only the *new* user content per call matters for this comparison;
    # take the last call, which carries every user segment sent so far.
    last_call_off = client_off.completions.calls[-1]["messages"]
    last_call_on = client_on.completions.calls[-1]["messages"]
    off_user_texts = [m["content"] for m in last_call_off if m["role"] == "user"]
    on_user_texts = [m["content"] for m in last_call_on if m["role"] == "user"]
    assert off_user_texts == on_user_texts == [
        "Segment A text.",
        "Segment B text.",
        "Segment C text.",
    ]


def test_provider_call_settings_unchanged_between_off_and_on():
    """Requirement 7: max_tokens (and, by extension, provider/model
    configuration -- fixed at the NebiusProvider layer, untouched here)
    must not vary with memory/policy presence.
    """

    responses_off = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_off, client_off = _provider_with(responses_off)
    runner_off = CompatibilityRunner(
        provider_off,
        max_tokens=77,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )
    runner_off.run(_small_scenario())

    responses_on = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_on, client_on = _provider_with(responses_on)
    runner_on = CompatibilityRunner(
        provider_on,
        max_tokens=77,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
        memory_payload=_FAKE_PROFILE_LIKE_PAYLOAD,
    )
    runner_on.run(_small_scenario())

    off_max_tokens = {call["max_tokens"] for call in client_off.completions.calls}
    on_max_tokens = {call["max_tokens"] for call in client_on.completions.calls}
    assert off_max_tokens == on_max_tokens == {77}


@pytest.mark.parametrize(
    "label,payload",
    [
        ("profile_like", _FAKE_PROFILE_LIKE_PAYLOAD),
        ("network_like", _FAKE_NETWORK_LIKE_PAYLOAD),
        ("numeric_labeled", _FAKE_NUMERIC_LABELED_PAYLOAD),
        ("unusual_unicode", _FAKE_UNICODE_PAYLOAD),
    ],
)
def test_payload_passed_onward_exactly_matches_loader_style_output(label, payload):
    """Requirements 3 + 4 + 5: whatever string is handed in as
    memory_payload -- including one with numbers/labels, and one with
    unusual Unicode -- comes out byte-for-byte identical in the
    message sent to the provider. This also demonstrates the consumer
    never parses or rewrites it: a JSON-shaped or numeric-shaped
    payload is never re-serialized, reformatted, or altered in any way.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        system_message=None,
        behavioral_use_policy=None,
        memory_context_label=None,
        memory_payload=payload,
        memory_payload_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )

    runner.run(_small_scenario())

    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert first_call_messages[0]["role"] == "system"
    assert first_call_messages[0]["content"] == payload
    # Character-for-character, not just logically equal.
    assert len(first_call_messages[0]["content"]) == len(payload)
    for expected_char, actual_char in zip(payload, first_call_messages[0]["content"]):
        assert expected_char == actual_char


def test_payload_integrity_check_passes_with_matching_hash():
    payload = _FAKE_NUMERIC_LABELED_PAYLOAD
    correct_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        memory_payload=payload,
        memory_payload_sha256=correct_hash,
    )

    result = runner.run(_small_scenario())

    assert result.completed is True
    assert result.memory_used is True


def test_payload_integrity_check_fails_closed_on_hash_mismatch_no_provider_call():
    """If the exact string about to be sent doesn't match the hash the
    caller says it should have, refuse to send it at all -- and never
    make a provider call in that turn.
    """

    payload = _FAKE_NUMERIC_LABELED_PAYLOAD
    wrong_hash = hashlib.sha256(b"a completely different fake string").hexdigest()
    responses = [_FakeResponse(_FakeMessage("should never be reached"))]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        memory_payload=payload,
        memory_payload_sha256=wrong_hash,
    )

    with pytest.raises(MemoryPayloadIntegrityError):
        runner.run(_small_scenario())

    assert len(fake_client.completions.calls) == 0


def test_payload_integrity_check_is_optional_and_skipped_when_no_hash_given():
    """Backward-compatible with M3D usage that never passed a hash: no
    hash supplied means no integrity check is performed, and the run
    proceeds exactly as it did before M4A.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        memory_payload=_FAKE_PROFILE_LIKE_PAYLOAD,
        memory_payload_sha256=None,
    )

    result = runner.run(_small_scenario())

    assert result.completed is True
    assert result.memory_used is True


def test_behavioral_use_policy_default_text_has_no_private_vocabulary():
    """The shipped default policy text itself must never mention
    Emotional Memory, SAE, XNET/XINJ, or any structural/schema term --
    it is a generic instruction about *any* supplied context.
    """

    forbidden_terms = [
        "Emotional Memory",
        "SAE",
        "XNET",
        "XINJ",
        "anchor",
        "kernel",
        "weight",
        "emotion_node",
    ]
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    for term in forbidden_terms:
        assert term.lower() not in lowered


def test_existing_tests_semantics_full_suite_still_reflects_pre_m4a_shapes():
    """A light end-to-end sanity check that the pre-M4A default
    (policy off, memory off) still reproduces the exact pre-M4A
    message shape used throughout the tests above this section.
    """

    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider)  # no new M4A args at all

    runner.run(_small_scenario())

    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert [m["role"] for m in first_call_messages] == ["system", "user"]
    assert first_call_messages[0]["content"] == (
        "You are participating in a short scripted conversation. Respond "
        "naturally and concisely to each message as it arrives."
    )


# --- scenario-grounding rule (M4B) ------------------------------------------
#
# These tests only inspect the policy TEXT and the runner's existing
# message-placement/symmetry behavior (already covered structurally
# above and unchanged by M4B). Per the M4B instructions, no test here
# attempts to simulate whether a mocked LLM actually obeys the policy --
# that requires a live model and is explicitly out of scope until a
# later, separate live test.

def test_policy_contains_a_current_conversation_grounding_constraint():
    """Requirement 5: the policy states a generic rule that concrete
    details must stay grounded in what the user actually provided in
    the current conversation.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "grounded in what the user has actually provided" in lowered
    assert "this conversation" in lowered
    # The specific categories of concrete detail the rule names.
    for category in ("people", "places", "events", "objects", "remembered scenes"):
        assert category in lowered


def test_policy_still_contains_no_private_vocabulary_after_m4b():
    """Requirement 6, re-checked against the M4B-extended text (not
    just the M4A prefix) -- the added grounding sentence must not
    introduce any private SAE vocabulary either.
    """

    forbidden_terms = [
        "Emotional Memory",
        "SAE",
        "XNET",
        "XINJ",
        "anchor",
        "kernel",
        "weight",
        "emotion_node",
    ]
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    for term in forbidden_terms:
        assert term.lower() not in lowered


def test_policy_does_not_prohibit_emotional_interpretation_or_relational_behavior():
    """Requirement 7: the grounding rule constrains invented concrete
    narrative facts, not emotional engagement -- the policy explicitly
    says background context may still shape interpretation, tone, and
    emotional/relational stance, and contains no blanket prohibition
    against emotional or relational behavior.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    # Affirmatively preserved.
    assert "interpretation" in lowered
    assert "tone" in lowered
    assert "emotional" in lowered and "stance" in lowered
    assert "relational" in lowered
    # No blanket ban on emotional or relational engagement.
    banned_phrasings = [
        "do not express emotion",
        "do not show emotion",
        "avoid emotion",
        "do not react emotionally",
        "no emotional",
        "without emotion",
        "do not engage emotionally",
    ]
    for phrasing in banned_phrasings:
        assert phrasing not in lowered


def test_existing_anti_recitation_instruction_remains_present_in_m4b_policy():
    """Requirement 8: the M4A anti-recitation sentence must still be
    present, verbatim, inside the M4B-extended policy -- M4B only adds
    to it, it does not remove or reword the existing function.
    """

    anti_recitation_sentence = (
        "Do not quote, list, summarize, or explain that context, or "
        "otherwise expose its content or structure, unless the user "
        "explicitly asks you to."
    )
    assert anti_recitation_sentence in DEFAULT_BEHAVIORAL_USE_POLICY

    # And the M4A opening framing sentence is likewise untouched.
    opening_sentence = (
        "Some conversations include supplied background context alongside "
        "the messages below."
    )
    assert DEFAULT_BEHAVIORAL_USE_POLICY.startswith(opening_sentence)


def test_grounding_rule_permits_exception_when_user_explicitly_asks():
    """The new rule, like the M4A rule before it, carries the same
    explicit-ask escape hatch -- it is not an absolute, unconditional
    prohibition.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "unless the user explicitly asks" in lowered


def test_m4b_policy_symmetry_matches_m4a_placement_and_role_shape():
    """Confirms M4B changed only the policy TEXT: message placement,
    role shape (all-system, isolated payload message), and OFF/ON
    symmetry are identical to the M4A structural tests above -- no
    context-placement change was introduced in M4B.
    """

    responses_off = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_off, client_off = _provider_with(responses_off)
    runner_off = CompatibilityRunner(
        provider_off,
        system_message=None,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )
    runner_off.run(_small_scenario())

    responses_on = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider_on, client_on = _provider_with(responses_on)
    runner_on = CompatibilityRunner(
        provider_on,
        system_message=None,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
        memory_payload=_FAKE_NETWORK_LIKE_PAYLOAD,
        memory_payload_sha256=hashlib.sha256(
            _FAKE_NETWORK_LIKE_PAYLOAD.encode("utf-8")
        ).hexdigest(),
    )
    runner_on.run(_small_scenario())

    off_roles = [m["role"] for m in client_off.completions.calls[0]["messages"]]
    on_roles = [m["role"] for m in client_on.completions.calls[0]["messages"]]
    assert off_roles == ["system", "user"]
    assert on_roles == ["system", "system", "system", "user"]
