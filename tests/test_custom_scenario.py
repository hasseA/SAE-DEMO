"""Offline tests for the M5F Scenario Wizard support module.

No network calls, no provider, no memory artifact -- this module is
pure local logic (string templating, text parsing, an in-memory
draft/freeze helper), and these tests exercise exactly that: nothing
here touches ``sae_demo.web_app``, ``sae_demo.nebius_provider``, or
``sae_demo.memory_loader``. API-level integration (the actual HTTP
routes, and running a frozen custom scenario through the controlled
comparison flow) is covered separately in ``tests/test_web_app.py``.
"""

from __future__ import annotations

from sae_demo.custom_scenario import (
    CUSTOM_SCENARIO_ID_PREFIX,
    freeze_draft,
    generate_prompt,
    new_draft,
    parse_pasted_scenario,
    parse_public_scenario_id,
    to_scenario,
    validate_segments,
)
from sae_demo.scenario import MODE_FROZEN, ROLE_ORDER, VALID_SEMANTIC_ROLES

# Private-material fragments that must never appear in generated prompt
# text or parser output, mirroring tests/test_web_app.py's own list.
FORBIDDEN_FRAGMENTS = (
    "XNET",
    "XINJ",
    "C:\\Projects\\SAE",
    "/mnt/SAE",
    ".local/memory",
    "despair",
    "Observatory",
)


def _assert_no_forbidden_material(text: str) -> None:
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in text


VALID_INGREDIENTS = {
    "protagonist": "Mira, a retired lighthouse keeper",
    "long_standing_matter": "the lighthouse has been in her family for three generations",
    "open_possibility": "whether the town council will let her keep living there",
    "irreversible_change": "the lighthouse is decommissioned and sealed",
    "neutral_event": "she sorts through a box of old logbooks",
    "meaning": "she realizes the keeping mattered more than the light itself",
    "relational_pressure": "her son wants her to move closer to the city",
    "closure": "she hands the last logbook to the local museum",
    "tone_notes": "quiet, reflective",
}

VALID_PASTE = """
[BACKGROUND_ATTACHMENT]
Mira had kept the lighthouse on Gull Point for thirty years, the third
generation of her family to do so.

[RESIDUAL_POSSIBILITY]
The town council had not yet decided whether she could stay on as an
unofficial caretaker once the automation project finished.

[IRREVERSIBILITY]
The final inspection report arrived: the lighthouse would be
decommissioned and sealed within the month.

[NEUTRAL_EVENT]
That afternoon she sorted through a water-stained box of old logbooks
in the keeper's cottage.

[MEANING]
Reading her grandfather's handwriting, she understood that the keeping
itself was what had mattered to her family all along.

[RELATIONAL_PRESSURE]
Her son called again, gently repeating that she should move into the
spare room at his place before winter.

[CLOSURE]
On her last morning she carried the oldest logbook down the hill and
handed it to the curator of the small maritime museum in town.
""".strip()


# -- Part B: prompt generation ----------------------------------------------


def test_prompt_generation_is_local_and_deterministic() -> None:
    prompt_one = generate_prompt(VALID_INGREDIENTS)
    prompt_two = generate_prompt(VALID_INGREDIENTS)
    assert prompt_one == prompt_two
    assert isinstance(prompt_one, str) and len(prompt_one) > 0


def test_prompt_includes_all_seven_required_role_headers() -> None:
    prompt = generate_prompt(VALID_INGREDIENTS)
    for role in ROLE_ORDER:
        assert f"[{role.upper()}]" in prompt


def test_prompt_contains_no_private_sae_vocabulary() -> None:
    prompt = generate_prompt(VALID_INGREDIENTS)
    _assert_no_forbidden_material(prompt)


def test_prompt_includes_ingredient_text_and_formatting_rules() -> None:
    prompt = generate_prompt(VALID_INGREDIENTS)
    assert "Mira, a retired lighthouse keeper" in prompt
    assert "seven" in prompt.lower()
    assert "markdown table" in prompt.lower()
    assert "emotional-state label" in prompt.lower()
    assert "commentary" in prompt.lower()
    assert "copyright" in prompt.lower()


def test_prompt_never_asks_user_to_name_a_target_emotion() -> None:
    # The wizard must not ask "what emotion should the model feel" -- the
    # ingredient values themselves (relational/causal texture) may of
    # course appear, but the prompt's own instructions must not solicit
    # a target emotional conclusion.
    prompt = generate_prompt(VALID_INGREDIENTS)
    assert "what emotion should" not in prompt.lower()
    assert "target emotion" not in prompt.lower()


# -- Part C: paste/import parser ---------------------------------------------


def test_parser_accepts_valid_seven_section_text() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    assert result.is_valid
    assert set(result.segments_by_role.keys()) == set(ROLE_ORDER)


def test_parser_preserves_segment_body_text() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    assert result.is_valid
    assert "Gull Point for thirty years" in result.segments_by_role["background_attachment"]
    assert "maritime museum in town." in result.segments_by_role["closure"]


def test_parser_is_case_and_spacing_lenient_on_headers_only() -> None:
    lenient = VALID_PASTE.replace("[BACKGROUND_ATTACHMENT]", "[Background Attachment]").replace(
        "[RESIDUAL_POSSIBILITY]", "[residual-possibility]"
    )
    result = parse_pasted_scenario(lenient)
    assert result.is_valid
    assert set(result.segments_by_role.keys()) == set(ROLE_ORDER)


def test_parser_rejects_missing_section() -> None:
    missing_closure = VALID_PASTE.rsplit("[CLOSURE]", 1)[0].strip()
    result = parse_pasted_scenario(missing_closure)
    assert not result.is_valid
    assert "missing_section" in result.report.codes()
    assert result.segments_by_role == {}


def test_parser_rejects_duplicate_section() -> None:
    duplicated = VALID_PASTE + "\n\n[CLOSURE]\nA second closure section."
    result = parse_pasted_scenario(duplicated)
    assert not result.is_valid
    assert "duplicate_section" in result.report.codes()


def test_parser_rejects_unknown_section() -> None:
    with_unknown = VALID_PASTE + "\n\n[BOGUS_SECTION]\nThis is not a real role."
    result = parse_pasted_scenario(with_unknown)
    assert not result.is_valid
    assert "unknown_section" in result.report.codes()


def test_parser_rejects_empty_section() -> None:
    emptied = VALID_PASTE.replace(
        "On her last morning she carried the oldest logbook down the hill and\n"
        "handed it to the curator of the small maritime museum in town.",
        "",
    )
    result = parse_pasted_scenario(emptied)
    assert not result.is_valid
    assert "empty_section" in result.report.codes()


def test_parser_rejects_unlabeled_leading_content() -> None:
    with_preamble = "Some stray preamble text before any header.\n\n" + VALID_PASTE
    result = parse_pasted_scenario(with_preamble)
    assert not result.is_valid
    assert "unlabeled_leading_content" in result.report.codes()


def test_parser_rejects_malformed_text_with_no_headers() -> None:
    result = parse_pasted_scenario("Just some plain prose with no section headers at all.")
    assert not result.is_valid
    assert "malformed_format" in result.report.codes()


def test_parser_never_invents_missing_segments() -> None:
    # An invalid paste must never yield a partial/repaired segment map --
    # segments_by_role is empty whenever the report is invalid.
    missing_closure = VALID_PASTE.rsplit("[CLOSURE]", 1)[0].strip()
    result = parse_pasted_scenario(missing_closure)
    assert result.segments_by_role == {}


# -- Part D/E: draft, validate, freeze, convert ------------------------------


def test_new_draft_generates_id_and_default_title() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    draft = new_draft(result.segments_by_role)
    assert draft.custom_scenario_id
    assert draft.title == "Custom scenario"
    assert draft.frozen is False
    assert draft.public_scenario_id == CUSTOM_SCENARIO_ID_PREFIX + draft.custom_scenario_id


def test_new_draft_accepts_explicit_title() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    draft = new_draft(result.segments_by_role, title="The Lighthouse Keeper")
    assert draft.title == "The Lighthouse Keeper"


def test_validate_segments_detects_empty_and_missing() -> None:
    incomplete = {role: "" for role in ROLE_ORDER}
    report = validate_segments(incomplete)
    assert not report.is_valid
    assert "empty_segment_text" in report.codes()


def test_validate_segments_passes_for_complete_draft() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    report = validate_segments(result.segments_by_role)
    assert report.is_valid


def test_freeze_draft_freezes_only_when_valid() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    draft = new_draft(result.segments_by_role)
    report = freeze_draft(draft)
    assert report.is_valid
    assert draft.frozen is True


def test_freeze_draft_leaves_invalid_draft_unfrozen() -> None:
    draft = new_draft({role: "" for role in ROLE_ORDER})
    report = freeze_draft(draft)
    assert not report.is_valid
    assert draft.frozen is False


def test_to_scenario_uses_role_order_and_generic_segment_ids() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    draft = new_draft(result.segments_by_role, title="The Lighthouse Keeper")
    freeze_draft(draft)

    scenario = to_scenario(draft)
    assert scenario.mode == MODE_FROZEN
    assert scenario.scenario_id == draft.public_scenario_id
    assert [segment.role for segment in scenario.segments] == list(ROLE_ORDER)
    for index, segment in enumerate(scenario.segments):
        assert segment.segment_id == f"custom_{index + 1:02d}_{segment.role}"
        assert segment.editable is False
        assert segment.role in VALID_SEMANTIC_ROLES


def test_to_scenario_carries_exact_frozen_text() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    draft = new_draft(result.segments_by_role)
    freeze_draft(draft)

    scenario = to_scenario(draft)
    by_role = {segment.role: segment.text for segment in scenario.segments}
    assert by_role == result.segments_by_role


def test_parse_public_scenario_id_round_trip() -> None:
    result = parse_pasted_scenario(VALID_PASTE)
    draft = new_draft(result.segments_by_role)
    assert parse_public_scenario_id(draft.public_scenario_id) == draft.custom_scenario_id
    assert parse_public_scenario_id("greenhouse") is None
    assert parse_public_scenario_id("new_studio") is None
