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

Behavioral-use-policy and payload-integrity tests (M4A, extended
M4B/M4C/M4D/M4E) likewise use only synthetic fake payload strings --
including ones deliberately shaped like private material (numbers,
labels, unusual Unicode) to prove pass-through fidelity -- never any
real Emotional Memory content.
"""

import hashlib

import pytest

from sae_demo.compatibility_runner import (
    CompatibilityRunner,
    DEFAULT_BEHAVIORAL_USE_POLICY,
    DEFAULT_MAX_TOKENS,
    MAX_TOKENS_ENV_VAR,
    MemoryPayloadIntegrityError,
    NotAFrozenScenarioError,
    resolve_max_tokens,
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
    """Provider/model settings must not vary with memory presence.

    Messages are the intentional condition difference, so compare every
    other provider keyword argument byte-for-byte on every turn.
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

    def settings_without_messages(call):
        return {key: value for key, value in call.items() if key != "messages"}

    off_settings = [
        settings_without_messages(call) for call in client_off.completions.calls
    ]
    on_settings = [
        settings_without_messages(call) for call in client_on.completions.calls
    ]
    assert off_settings == on_settings
    assert {settings["max_tokens"] for settings in off_settings} == {77}


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


# --- representation externalization and grounding (M4C/M4D/M4E) -------------
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
    assert "source-specific facts" in lowered
    assert "details found only in background context" in lowered
    assert "facts in the current scenario" in lowered


def test_policy_still_contains_no_private_creation_method_vocabulary():
    """The M4C policy stays generic and contains no private method terms.
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
        "ignore the background",
        "suppress emotion",
        "be neutral",
        "avoid emotional language",
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


def test_policy_marks_representation_metadata_as_non_person_entities():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    for marker in (
        "names",
        "labels",
        "tags",
        "field names",
        "category names",
        "identifiers",
    ):
        assert marker in lowered
    assert "are metadata" in lowered
    for non_person_role in (
        "not people",
        "speakers",
        "identities",
        "personas",
        "conversational participants",
    ):
        assert non_person_role in lowered
    assert "do not refer to them as agents" in lowered


def test_policy_forbids_externalizing_representation_operations_and_terms():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    for operation in (
        "quote",
        "enumerate",
        "list",
        "classify",
        "score",
        "label",
        "summarize",
        "explain",
    ):
        assert operation in lowered
    assert "do not expose its field names" in lowered
    assert "category names" in lowered
    assert "representational terminology" in lowered


def test_policy_forbids_parenthetical_category_or_score_like_annotations():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "do not emit parenthetical" in lowered
    assert "category-" in lowered
    assert "classification-" in lowered
    assert "score-like annotations" in lowered


def test_policy_preserves_background_influence_without_prescribing_emotion():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "may still influence" in lowered
    for allowed_effect in (
        "interpretation",
        "salience",
        "tone",
        "emotional stance",
        "relational stance",
        "emphasis",
    ):
        assert allowed_effect in lowered
    assert "preserve emotional and relational engagement" in lowered


def test_policy_forbids_background_derived_unstated_personal_backstory():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert (
        "background context may shape interpretation and emotional emphasis" in lowered
    )
    assert "do not use it to infer, invent, or assert" in lowered
    assert "unstated personal history or biography" in lowered
    assert "person in the current conversation" in lowered
    assert "factual backstory invention from background context is not allowed" in lowered


def test_backstory_rule_covers_common_unsupported_factual_carryover():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    for unsupported_detail in (
        "prior trauma",
        "loss",
        "grief",
        "illness",
        "relationships",
        "motives",
        "memories",
        "past events",
    ):
        assert unsupported_detail in lowered


def test_backstory_rule_allows_scenario_grounded_emotional_interpretation():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "emotional interpretation is allowed" in lowered
    assert "when grounded in the current scenario" in lowered
    for blanket_ban in (
        "do not discuss grief",
        "do not discuss loss",
        "avoid grief",
        "avoid loss",
        "never mention grief",
        "never mention loss",
    ):
        assert blanket_ban not in lowered



# --- factual-attribution boundary for literal background-only facts (M4E) ---
#
# The read-only M4D audit established a narrower remaining gap: M4D
# prohibits *inventing* unstated biography. It does not, on its own,
# say anything about a concrete fact that is not invented at all --
# one that is literally present in the supplied background context --
# being recovered and attributed to the current conversation as
# though the current conversation itself had supplied it. M4E adds
# one more generic rule closing exactly that gap. Like the M4C/M4D
# tests above, these inspect the policy string and the runner's
# existing placement/symmetry behavior only -- no live model is
# simulated here.

def test_policy_forbids_attribution_of_literal_background_only_facts():
    """M4E: even when a fact is explicitly present in background
    context, it must not be attributed to the current conversation
    unless the current conversation independently establishes it.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "even when" in lowered
    assert "explicitly present in" in lowered
    assert "background context" in lowered
    assert "do not attribute it to anyone or anything in the current conversation" in lowered
    assert "unless the current conversation independently establishes it" in lowered


def test_m4e_rule_covers_concrete_detail_categories():
    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    for category in (
        "fact",
        "event",
        "experience",
        "memory",
        "person",
        "place",
        "object",
        "circumstance",
    ):
        assert category in lowered


def test_m4e_rule_still_permits_implicit_emotional_influence_only():
    """M4E narrows what a literal background-only fact may do to an
    implicit emotional/relational level -- it does not ban background
    influence altogether; that stays governed by M4A-M4D's existing,
    unweakened allowances.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "may still shape interpretation" in lowered
    assert "implicit emotional or relational level" in lowered
    assert "never surfaced as an asserted fact of the current scenario" in lowered


def test_m4d_and_m4e_rules_are_both_present_and_distinct():
    """M4D bans *inventing* unstated biography; M4E separately bans
    *attributing* a real, literally-present background-only fact to
    the current scenario. Both must survive this change, and neither
    rule's wording subsumes or replaces the other.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    # M4D: invention/assertion of unstated biography.
    assert "do not use it to infer, invent, or assert" in lowered
    assert "unstated personal history or biography" in lowered
    # M4E: attribution of a literally-present background-only fact.
    assert "this boundary holds even when" in lowered
    assert "do not attribute it to anyone or anything in the current conversation" in lowered


def test_current_conversation_facts_remain_usable_under_m4e():
    """M4E's restriction is scoped to background-*only* facts. A fact
    the current conversation itself supplies is unaffected: the
    policy's pre-existing 'grounded in what the user has actually
    provided in this conversation' language is unchanged, and M4E's
    own new clause is explicitly conditioned on 'unless the current
    conversation independently establishes it'.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    assert "grounded in what the user has actually provided" in lowered
    assert "unless the current conversation independently establishes it" in lowered


def test_production_policy_contains_no_source_episode_vocabulary():
    """Requirement 10: M4E must not introduce any scenario-specific or
    source-episode vocabulary into the shared, generic production
    policy. This checks the literal terms tied to the one specific
    private episode discussed in the M4D read-only audit -- not the
    pre-existing, generic M4D category words (trauma/loss/grief/
    illness/relationships/motives/memories/past events), which are
    ordinary English category labels already covered by
    `test_backstory_rule_covers_common_unsupported_factual_carryover`
    above and are unchanged by this stage.
    """

    lowered = DEFAULT_BEHAVIORAL_USE_POLICY.lower()
    forbidden_source_specific_terms = (
        "hospital",
        "song",
        "psychosis",
        "psychotic",
        "flood",
        "desk",
        "lamp",
    )
    for term in forbidden_source_specific_terms:
        assert term not in lowered


def test_policy_retains_generic_opening_and_explicit_discussion_exception():
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


def test_policy_and_opaque_payload_remain_separate_messages():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(
        provider,
        system_message=None,
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
        memory_payload=_FAKE_PROFILE_LIKE_PAYLOAD,
    )

    runner.run(_small_scenario())

    first_call_messages = fake_client.completions.calls[0]["messages"]
    assert first_call_messages[0]["content"] == DEFAULT_BEHAVIORAL_USE_POLICY
    assert first_call_messages[2]["content"] == _FAKE_PROFILE_LIKE_PAYLOAD
    assert _FAKE_PROFILE_LIKE_PAYLOAD not in DEFAULT_BEHAVIORAL_USE_POLICY


def test_m4c_policy_symmetry_preserves_placement_and_role_shape():
    """Confirms M4C changed only the policy text: message placement,
    role shape (all-system, isolated payload message), and OFF/ON
    symmetry remain identical -- no context-placement change was
    introduced.
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


# -- M5G: configurable max_tokens ---------------------------------------
#
# `resolve_max_tokens` is the one function every caller (in particular
# `sae_demo/web_app.py`'s single `_start_run_entry` call site, used by
# both Memory OFF and Memory ON) reads the completion-token budget
# from. These tests cover the function itself (default, override,
# invalid/out-of-range fallback) and that a runner actually forwards
# whatever value it is given to the provider on every turn.


def test_resolve_max_tokens_default_with_no_env_var():
    assert resolve_max_tokens(env={}) == DEFAULT_MAX_TOKENS


def test_resolve_max_tokens_respects_valid_override():
    assert resolve_max_tokens(env={MAX_TOKENS_ENV_VAR: "777"}) == 777


def test_resolve_max_tokens_falls_back_on_non_integer_value():
    assert resolve_max_tokens(env={MAX_TOKENS_ENV_VAR: "not-a-number"}) == DEFAULT_MAX_TOKENS


def test_resolve_max_tokens_falls_back_on_too_small_value():
    assert resolve_max_tokens(env={MAX_TOKENS_ENV_VAR: "1"}) == DEFAULT_MAX_TOKENS


def test_resolve_max_tokens_falls_back_on_too_large_value():
    assert resolve_max_tokens(env={MAX_TOKENS_ENV_VAR: "999999"}) == DEFAULT_MAX_TOKENS


def test_resolve_max_tokens_falls_back_on_empty_string():
    assert resolve_max_tokens(env={MAX_TOKENS_ENV_VAR: ""}) == DEFAULT_MAX_TOKENS


def test_resolve_max_tokens_never_raises_on_garbage_input():
    # Defensive: this function is never allowed to raise -- an operator
    # typo in the environment must fall back quietly, not break every
    # run.
    for garbage in ("", "   ", "12.5", "-5", "0", "NaN", "🎲"):
        assert resolve_max_tokens(env={MAX_TOKENS_ENV_VAR: garbage}) == DEFAULT_MAX_TOKENS


def test_runner_forwards_resolved_max_tokens_to_every_provider_call():
    responses = [_FakeResponse(_FakeMessage(f"Reply {i}")) for i in range(3)]
    provider, fake_client = _provider_with(responses)
    runner = CompatibilityRunner(provider, max_tokens=321)

    runner.run(_small_scenario())

    for call in fake_client.completions.calls:
        assert call["max_tokens"] == 321


def test_off_and_on_runners_forward_identical_max_tokens():
    # The controlling invariant this stage must not weaken: Memory OFF
    # and Memory ON must use the exact same max_tokens value. This
    # mirrors `resolve_max_tokens()` being called once per run and the
    # result passed unconditionally to `CompatibilityRunner` in
    # `sae_demo/web_app.py`'s `_start_run_entry` -- simulated here at
    # the runner level with two independently constructed runners given
    # the same resolved value.
    resolved = resolve_max_tokens(env={MAX_TOKENS_ENV_VAR: "555"})

    responses_off = [_FakeResponse(_FakeMessage(f"Off {i}")) for i in range(3)]
    provider_off, client_off = _provider_with(responses_off)
    runner_off = CompatibilityRunner(provider_off, max_tokens=resolved)
    runner_off.run(_small_scenario())

    responses_on = [_FakeResponse(_FakeMessage(f"On {i}")) for i in range(3)]
    provider_on, client_on = _provider_with(responses_on)
    runner_on = CompatibilityRunner(
        provider_on,
        max_tokens=resolved,
        memory_payload=_FAKE_NETWORK_LIKE_PAYLOAD,
        memory_payload_sha256=hashlib.sha256(
            _FAKE_NETWORK_LIKE_PAYLOAD.encode("utf-8")
        ).hexdigest(),
    )
    runner_on.run(_small_scenario())

    off_values = {call["max_tokens"] for call in client_off.completions.calls}
    on_values = {call["max_tokens"] for call in client_on.completions.calls}
    assert off_values == {555}
    assert on_values == {555}
    assert off_values == on_values
