"""Offline tests for the Memory-OFF synthetic compatibility runner.

No network calls. The Nebius provider's OpenAI client is replaced
with a fake that returns pre-scripted responses (or raises) per call,
so the full runner -> provider integration is exercised without any
real API access.
"""

import pytest

from sae_demo.compatibility_runner import (
    CompatibilityRunner,
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
