"""Offline tests for the backend scenario engine.

No network calls, no provider involved — the engine is exercised only
against the two synthetic fixtures in
tests/fixtures/synthetic_scenarios.py and small inline scenarios.
"""

import pytest

from sae_demo.scenario import MODE_FROZEN, MODE_INTERACTIVE, Scenario, ScenarioSegment
from sae_demo.scenario_engine import (
    FrozenRunEditError,
    NoMoreSegmentsError,
    ScenarioEngine,
    ScenarioValidationError,
    SegmentAlreadySentError,
    SegmentNotEditableError,
    UnknownSegmentError,
)

from tests.fixtures.synthetic_scenarios import (
    build_benign_transition_fixture,
    build_irreversible_loss_fixture,
)


# --- loading -------------------------------------------------------------

def test_load_valid_scenario_from_each_fixture():
    for build in (build_irreversible_loss_fixture, build_benign_transition_fixture):
        engine = ScenarioEngine(build(mode=MODE_FROZEN))
        assert not engine.is_complete
        assert len(engine.scenario.segments) == 7


def test_loading_malformed_scenario_raises_validation_error():
    malformed = Scenario(
        scenario_id="",
        title="",
        description="",
        segments=(),
        mode="bogus",
    )

    with pytest.raises(ScenarioValidationError) as exc_info:
        ScenarioEngine(malformed)

    codes = exc_info.value.report.codes()
    assert "missing_scenario_id" in codes
    assert "missing_title" in codes
    assert "no_segments" in codes
    assert "invalid_mode" in codes


def test_preserves_segment_order():
    scenario = build_irreversible_loss_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)

    expected_order = tuple(segment.segment_id for segment in scenario.segments)
    assert engine.run_trace().segment_order == expected_order


# --- traversal -------------------------------------------------------------

def test_preview_next_segment_does_not_advance():
    engine = ScenarioEngine(build_benign_transition_fixture(mode=MODE_FROZEN))

    first_preview = engine.preview_next_segment()
    second_preview = engine.preview_next_segment()

    assert first_preview.segment_id == second_preview.segment_id == "studio_01_background"
    assert not engine.is_complete
    assert engine.run_trace().sent_segments == ()


def test_advance_sends_one_segment_and_moves_position():
    scenario = build_benign_transition_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)

    record = engine.advance()

    assert record.segment_id == "studio_01_background"
    assert record.text_sent == scenario.segments[0].text
    assert record.was_edited is False
    assert engine.preview_next_segment().segment_id == "studio_02_possibility"


def test_full_replay_sends_every_segment_in_order():
    scenario = build_irreversible_loss_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)

    sent_ids = []
    while not engine.is_complete:
        record = engine.advance()
        sent_ids.append(record.segment_id)

    expected_order = tuple(segment.segment_id for segment in scenario.segments)
    assert tuple(sent_ids) == expected_order
    assert engine.run_trace().sent_segments[-1].segment_id == expected_order[-1]


def test_end_of_scenario_preview_and_advance_raise():
    scenario = build_benign_transition_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)

    for _ in scenario.segments:
        engine.advance()

    assert engine.is_complete
    with pytest.raises(NoMoreSegmentsError):
        engine.preview_next_segment()
    with pytest.raises(NoMoreSegmentsError):
        engine.advance()


# --- frozen mode -----------------------------------------------------------

def test_frozen_mode_rejects_edits():
    scenario = build_irreversible_loss_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)

    with pytest.raises(FrozenRunEditError):
        engine.edit_upcoming_segment("greenhouse_02_possibility", "changed text")


def test_frozen_mode_preserves_exact_text_through_full_replay():
    scenario = build_irreversible_loss_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)

    while not engine.is_complete:
        engine.advance()

    trace = engine.run_trace()
    for original_segment, record in zip(scenario.segments, trace.sent_segments):
        assert record.text_sent == original_segment.text
        assert record.was_edited is False
    assert trace.revisions == ()


# --- interactive mode --------------------------------------------------------

def test_interactive_mode_accepts_edit_of_unsent_segment():
    scenario = build_benign_transition_fixture(mode=MODE_INTERACTIVE)
    engine = ScenarioEngine(scenario)

    engine.advance()  # send studio_01_background
    revision = engine.edit_upcoming_segment(
        "studio_02_possibility", "A gently reworded version of the possibility beat."
    )

    assert revision.segment_id == "studio_02_possibility"
    assert revision.revision_sequence == 1
    preview = engine.preview_next_segment()
    assert preview.text == "A gently reworded version of the possibility beat."


def test_exact_revision_provenance_is_preserved():
    scenario = build_benign_transition_fixture(mode=MODE_INTERACTIVE)
    engine = ScenarioEngine(scenario)
    original_text = scenario.segments[0].text

    engine.edit_upcoming_segment("studio_01_background", "First edit.")
    engine.edit_upcoming_segment("studio_01_background", "Second edit.")

    trace = engine.run_trace()
    assert len(trace.revisions) == 2

    first, second = trace.revisions
    assert first.segment_id == second.segment_id == "studio_01_background"
    assert first.original_text == original_text
    assert second.original_text == original_text  # original never mutates
    assert first.revised_text == "First edit."
    assert second.revised_text == "Second edit."
    assert first.revision_sequence == 1
    assert second.revision_sequence == 2


def test_sent_segment_cannot_be_edited():
    scenario = build_benign_transition_fixture(mode=MODE_INTERACTIVE)
    engine = ScenarioEngine(scenario)

    engine.advance()  # sends studio_01_background

    with pytest.raises(SegmentAlreadySentError):
        engine.edit_upcoming_segment("studio_01_background", "too late")


def test_editing_non_editable_segment_is_rejected():
    segments = (
        ScenarioSegment(
            segment_id="locked",
            role="irreversibility",
            text="This segment is fixed.",
            editable=False,
        ),
        ScenarioSegment(
            segment_id="open",
            role="closure",
            text="This one can be edited.",
            editable=True,
        ),
    )
    scenario = Scenario(
        scenario_id="lock_test",
        title="Lock Test",
        description="",
        segments=segments,
        mode=MODE_INTERACTIVE,
    )
    engine = ScenarioEngine(scenario)

    with pytest.raises(SegmentNotEditableError):
        engine.edit_upcoming_segment("locked", "trying anyway")


def test_editing_unknown_segment_raises():
    engine = ScenarioEngine(build_benign_transition_fixture(mode=MODE_INTERACTIVE))

    with pytest.raises(UnknownSegmentError):
        engine.edit_upcoming_segment("does_not_exist", "text")


# --- run trace / model response ------------------------------------------

def test_run_trace_records_exact_sent_text_including_edits():
    scenario = build_irreversible_loss_fixture(mode=MODE_INTERACTIVE)
    engine = ScenarioEngine(scenario)

    engine.edit_upcoming_segment(
        "greenhouse_01_background", "An edited opening beat for this run."
    )
    record = engine.advance()

    trace = engine.run_trace()
    assert trace.sent_segments[0] is record
    assert record.text_sent == "An edited opening beat for this run."
    assert record.original_text == scenario.segments[0].text
    assert record.was_edited is True


def test_record_model_response_attaches_to_sent_segment():
    engine = ScenarioEngine(build_benign_transition_fixture(mode=MODE_FROZEN))
    engine.advance()

    updated = engine.record_model_response("studio_01_background", "Model reply text.")

    assert updated.model_response == "Model reply text."
    trace = engine.run_trace()
    assert trace.sent_segments[0].model_response == "Model reply text."


def test_record_model_response_for_unsent_segment_raises():
    engine = ScenarioEngine(build_benign_transition_fixture(mode=MODE_FROZEN))

    with pytest.raises(UnknownSegmentError):
        engine.record_model_response("studio_01_background", "too early")
