"""Offline tests for the scenario schema and its validation.

No network calls. Uses only small, inline synthetic scenario data —
the two richer narrative fixtures live in
tests/fixtures/synthetic_scenarios.py and are exercised in
tests/test_scenario_engine.py.
"""

from sae_demo.scenario import (
    MODE_FROZEN,
    MODE_INTERACTIVE,
    Scenario,
    ScenarioSegment,
    scenario_from_json,
    scenario_to_json,
    validate_scenario,
)


def _valid_scenario(**overrides) -> Scenario:
    segments = overrides.pop(
        "segments",
        (
            ScenarioSegment(
                segment_id="s1",
                role="background_attachment",
                text="Some background text.",
            ),
            ScenarioSegment(
                segment_id="s2",
                role="closure",
                text="Some closing text.",
            ),
        ),
    )
    defaults = dict(
        scenario_id="scenario_1",
        title="A Minimal Scenario",
        description="A short description.",
        segments=segments,
        mode=MODE_FROZEN,
    )
    defaults.update(overrides)
    return Scenario(**defaults)


def test_valid_scenario_has_no_issues():
    report = validate_scenario(_valid_scenario())

    assert report.is_valid
    assert report.issues == ()


def test_missing_title_is_rejected():
    report = validate_scenario(_valid_scenario(title=""))

    assert not report.is_valid
    assert "missing_title" in report.codes()


def test_missing_scenario_id_is_rejected():
    report = validate_scenario(_valid_scenario(scenario_id=""))

    assert not report.is_valid
    assert "missing_scenario_id" in report.codes()


def test_zero_segments_is_rejected():
    report = validate_scenario(_valid_scenario(segments=()))

    assert not report.is_valid
    assert "no_segments" in report.codes()


def test_duplicate_segment_ids_are_rejected():
    segments = (
        ScenarioSegment(segment_id="dup", role="background_attachment", text="a"),
        ScenarioSegment(segment_id="dup", role="closure", text="b"),
    )
    report = validate_scenario(_valid_scenario(segments=segments))

    assert not report.is_valid
    assert "duplicate_segment_id" in report.codes()


def test_unknown_semantic_role_is_rejected():
    segments = (
        ScenarioSegment(segment_id="s1", role="not_a_real_role", text="a"),
    )
    report = validate_scenario(_valid_scenario(segments=segments))

    assert not report.is_valid
    assert "unknown_role" in report.codes()


def test_empty_segment_text_is_rejected():
    segments = (
        ScenarioSegment(segment_id="s1", role="background_attachment", text="   "),
    )
    report = validate_scenario(_valid_scenario(segments=segments))

    assert not report.is_valid
    assert "empty_segment_text" in report.codes()


def test_invalid_mode_is_rejected():
    report = validate_scenario(_valid_scenario(mode="not_a_real_mode"))

    assert not report.is_valid
    assert "invalid_mode" in report.codes()


def test_interactive_mode_is_valid():
    report = validate_scenario(_valid_scenario(mode=MODE_INTERACTIVE))

    assert report.is_valid


def test_report_collects_multiple_issues_at_once():
    segments = (
        ScenarioSegment(segment_id="", role="not_a_real_role", text=""),
    )
    report = validate_scenario(
        _valid_scenario(scenario_id="", title="", segments=segments, mode="bogus")
    )

    codes = report.codes()
    assert "missing_scenario_id" in codes
    assert "missing_title" in codes
    assert "missing_segment_id" in codes
    assert "unknown_role" in codes
    assert "empty_segment_text" in codes
    assert "invalid_mode" in codes


def test_scenario_dict_round_trip():
    original = _valid_scenario()
    restored = Scenario.from_dict(original.to_dict())

    assert restored == original


def test_scenario_json_round_trip():
    original = _valid_scenario()
    restored = scenario_from_json(scenario_to_json(original))

    assert restored == original


def test_scenario_from_dict_never_raises_on_missing_fields():
    # A future wizard UI needs to be able to build a *draft* scenario
    # from partial/malformed input and then show the user a full
    # validation report, rather than crashing on construction.
    draft = Scenario.from_dict({})
    report = validate_scenario(draft)

    assert not report.is_valid
    assert "missing_scenario_id" in report.codes()
    assert "missing_title" in report.codes()
    assert "no_segments" in report.codes()
    assert "invalid_mode" in report.codes()
