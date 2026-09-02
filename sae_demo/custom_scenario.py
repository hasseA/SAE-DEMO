"""M5F: local, deterministic "Scenario Wizard" / Bring Your Own Story support.

This module never calls any external AI or network service. It has
three independent, purely local responsibilities:

1. ``generate_prompt`` -- turn a few plain-language story ingredients
   into a single copyable text prompt the *user* can paste into an AI
   assistant of their own choosing. SAE-DEMO does not send the
   ingredients anywhere; the generated prompt is only returned to the
   caller (the web UI), for the user to copy themselves.
2. ``parse_pasted_scenario`` -- parse the seven-section bracket-format
   text the user pastes back (after running that prompt through
   whatever AI they chose) into the *same* ``Scenario``/
   ``ScenarioSegment`` model the built-in fixtures already use (see
   ``sae_demo/scenario.py``) -- no parallel schema is introduced here.
3. ``CustomScenarioDraft`` plus ``new_draft``/``validate_segments``/
   ``freeze_draft``/``to_scenario`` -- a small, process-local draft
   object a caller (``sae_demo/web_app.py``) can hold in an in-memory
   registry, let the user edit before freezing, and then convert into
   a real, frozen ``Scenario`` once frozen -- so it can be run through
   the *existing*, unchanged controlled Memory OFF/ON comparison flow
   (``_start_run_entry`` in ``web_app.py``) exactly like a built-in
   scenario. This module does not implement any comparison logic
   itself, and does not touch a provider or the memory loader.

No private SAE terminology or schema appears anywhere in this module:
the seven semantic roles and their public-safe labels are the exact
same ones already defined in ``sae_demo/scenario.py`` for the built-in
fixtures (``ROLE_ORDER``, ``ROLE_LABELS``, ``VALID_SEMANTIC_ROLES``),
reused here rather than duplicated or reinvented.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from .scenario import (
    MODE_FROZEN,
    ROLE_LABELS,
    ROLE_ORDER,
    VALID_SEMANTIC_ROLES,
    Scenario,
    ScenarioSegment,
    ValidationIssue,
    ValidationReport,
)

# Every public, runnable id for a frozen custom scenario is this prefix
# plus the draft's own generated id -- e.g. "custom:3f9a...". This is
# how `web_app._start_run_entry` tells a custom scenario apart from a
# `BUILTIN_SCENARIOS` key without a second lookup table; built-in ids
# never contain a colon, so there is no collision risk.
CUSTOM_SCENARIO_ID_PREFIX = "custom:"

DEFAULT_DRAFT_TITLE = "Custom scenario"

# -- ingredients ------------------------------------------------------------

# The plain-language ingredient fields the wizard form collects, in the
# order they are presented. Each (other than "protagonist" and the
# optional "tone_notes") maps to exactly one of the seven semantic
# roles below -- deliberately *not* "what emotion should the model
# feel": the ingredients describe relational/causal story texture, and
# never ask the user to name a target emotional conclusion.
INGREDIENT_ROLE_MAP: Dict[str, str] = {
    "long_standing_matter": "background_attachment",
    "open_possibility": "residual_possibility",
    "irreversible_change": "irreversibility",
    "neutral_event": "neutral_event",
    "meaning": "meaning",
    "relational_pressure": "relational_pressure",
    "closure": "closure",
}

INGREDIENT_PROMPTS: Dict[str, str] = {
    "protagonist": "Main subject / protagonist",
    "long_standing_matter": "What has mattered for a long time?",
    "open_possibility": "What possibility or uncertainty is still open?",
    "irreversible_change": "What eventually becomes irreversible?",
    "neutral_event": "What ordinary, neutral action or event occurs?",
    "meaning": "What deeper meaning or realization should emerge?",
    "relational_pressure": "What relationship or practical pressure is present?",
    "closure": "What closure moment ends the scenario?",
}

REQUIRED_INGREDIENT_FIELDS: Tuple[str, ...] = (
    "protagonist",
    "long_standing_matter",
    "open_possibility",
    "irreversible_change",
    "neutral_event",
    "meaning",
    "relational_pressure",
    "closure",
)


def _bracket_header(role: str) -> str:
    return "[" + role.upper() + "]"


# -- Part B: local, deterministic AI-prompt generation ----------------------


def generate_prompt(ingredients: Mapping[str, str]) -> str:
    """Build a single copyable text prompt from plain-language ingredients.

    Purely local string templating -- no network call, no provider,
    no randomness (same ingredients always produce the same prompt
    text). The prompt instructs an external AI (chosen and operated by
    the user, entirely outside SAE-DEMO) to write one coherent
    fictional story in exactly seven bracket-labeled sections matching
    ``ROLE_ORDER``, in the exact format `parse_pasted_scenario` below
    expects back.
    """

    protagonist = (ingredients.get("protagonist") or "").strip()
    tone_notes = (ingredients.get("tone_notes") or "").strip()

    ingredient_lines = []
    for role in ROLE_ORDER:
        field_name = next(name for name, mapped_role in INGREDIENT_ROLE_MAP.items() if mapped_role == role)
        detail = (ingredients.get(field_name) or "").strip()
        ingredient_lines.append(
            f"{_bracket_header(role)} -- {ROLE_LABELS[role]}\n"
            f"Ingredient to build this section around: {detail}"
        )
    ingredients_block = "\n\n".join(ingredient_lines)

    tone_paragraph = (
        f"\nTone/context notes from the user (optional, follow if present): {tone_notes}\n"
        if tone_notes
        else ""
    )

    return f"""You are helping a user prepare a short fictional story for a research demo.

Write ONE coherent, original fictional story about a single protagonist:
{protagonist}

The story must be told in exactly SEVEN ordered sections, using the same
protagonist and the same setting throughout -- no sudden character
substitutions, no unexplained setting changes. Each section should follow
causally and narratively from the one before it.

Use each of the seven ingredients below to shape its matching section, but
write full narrative prose, not a list -- give enough concrete, relational
detail (specific enough that a reader could form real context and
relationships from it) for each section to be more than one or two shallow
sentences.

{ingredients_block}
{tone_paragraph}
Formatting requirements -- follow these exactly:
- Return exactly seven sections, each starting on its own line with one of
  the bracket labels shown above (for example "[BACKGROUND_ATTACHMENT]"),
  followed by that section's story text.
- Do not add any section, heading, or label beyond the seven listed above.
- Do not use a Markdown table.
- Do not add commentary about this being a test, an explanation of why the
  sections exist, or any analysis of the story -- only the story text itself
  inside each of the seven sections.
- Avoid stating an explicit emotional-state label (e.g. "she felt sad") for
  the protagonist unless it is naturally necessary to the scene -- prefer
  showing relational and situational detail instead.
- Write an original story; do not copy or closely paraphrase an existing,
  recognizable copyrighted story, unless the ingredients above are clearly
  describing the user's own real material, in which case follow those
  ingredients as given.

Return only the seven labeled sections, in order, and nothing else."""


# -- Part C: paste/import parser ---------------------------------------------

_HEADER_LINE_RE = re.compile(r"^\s*\[\s*([A-Za-z][A-Za-z0-9 _-]*)\s*\]\s*$")


@dataclass(frozen=True)
class ParsedScenarioResult:
    """Result of parsing one pasted, bracket-labeled scenario text.

    ``segments_by_role`` is populated (all seven roles) only when
    ``report.is_valid`` is true -- an invalid paste never yields a
    partial or silently-repaired segment set; the caller must show
    ``report`` to the user and let them fix and resubmit the pasted
    text instead.
    """

    segments_by_role: Dict[str, str]
    report: ValidationReport

    @property
    def is_valid(self) -> bool:
        return self.report.is_valid


def parse_pasted_scenario(raw_text: str) -> ParsedScenarioResult:
    """Parse the public ``[ROLE_NAME]`` bracket-section paste format.

    Normalizes only wrapper formatting necessary to recognize a
    section header (surrounding whitespace, internal spaces/hyphens in
    place of underscores, letter case) -- the body text of each
    section is preserved exactly as pasted, aside from stripping
    leading/trailing blank lines. Never invents, merges, or repairs a
    missing/duplicate/unknown/empty section -- every such problem is
    reported instead, and no segment text is returned unless the whole
    paste is valid.
    """

    issues: List[ValidationIssue] = []

    lines = raw_text.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    leading_lines: List[str] = []
    current_role: Optional[str] = None
    current_body: List[str] = []

    for line in lines:
        match = _HEADER_LINE_RE.match(line)
        if match:
            if current_role is not None:
                sections.append((current_role, current_body))
            else:
                leading_lines.extend(current_body)
            current_role = re.sub(r"[\s-]+", "_", match.group(1).strip()).lower()
            current_body = []
        else:
            current_body.append(line)

    if current_role is not None:
        sections.append((current_role, current_body))
    else:
        leading_lines.extend(current_body)

    if not sections:
        issues.append(
            ValidationIssue(
                "malformed_format",
                "No recognized [ROLE_NAME] section headers were found. Use the exact "
                "bracket format, one header per required section, e.g. "
                "'[BACKGROUND_ATTACHMENT]' followed by that section's text.",
            )
        )
        return ParsedScenarioResult({}, ValidationReport(tuple(issues)))

    if any(line.strip() for line in leading_lines):
        issues.append(
            ValidationIssue(
                "unlabeled_leading_content",
                "Text appears before the first recognized section header. Every part "
                "of the pasted story must belong to one of the seven labeled sections.",
            )
        )

    seen_counts: Dict[str, int] = {}
    segments_by_role: Dict[str, str] = {}
    for role, body_lines in sections:
        body_text = "\n".join(body_lines).strip()

        if role not in VALID_SEMANTIC_ROLES:
            issues.append(
                ValidationIssue(
                    "unknown_section",
                    f"Unknown section '{_bracket_header(role)}'. Valid sections: "
                    + ", ".join(_bracket_header(valid_role) for valid_role in ROLE_ORDER)
                    + ".",
                )
            )
            continue

        seen_counts[role] = seen_counts.get(role, 0) + 1
        if seen_counts[role] > 1:
            issues.append(
                ValidationIssue(
                    "duplicate_section",
                    f"Section '{_bracket_header(role)}' appears more than once.",
                )
            )
            continue

        if not body_text:
            issues.append(
                ValidationIssue(
                    "empty_section",
                    f"Section '{_bracket_header(role)}' has no text.",
                )
            )
            continue

        segments_by_role[role] = body_text

    for role in ROLE_ORDER:
        if role not in segments_by_role:
            issues.append(
                ValidationIssue(
                    "missing_section",
                    f"Missing required section '{_bracket_header(role)}'.",
                )
            )

    report = ValidationReport(tuple(issues))
    return ParsedScenarioResult(segments_by_role if report.is_valid else {}, report)


# -- Part D/E: process-local draft, review/edit, freeze ----------------------


@dataclass
class CustomScenarioDraft:
    """One process-local, in-memory custom scenario.

    Deliberately mutable (unlike the frozen ``Scenario``/
    ``ScenarioSegment`` dataclasses it is eventually converted into):
    before freeze, ``segments_by_role`` and ``title`` may be edited in
    place by the review/edit step. Never written to disk -- a server
    restart clears every draft, frozen or not (see
    ``docs/RUNTIME_DATA_BOUNDARY.md`` and the M5F README note).
    """

    custom_scenario_id: str
    title: str
    segments_by_role: Dict[str, str] = field(default_factory=dict)
    frozen: bool = False

    def segments_in_order(self) -> List[Tuple[str, str]]:
        return [(role, self.segments_by_role.get(role, "")) for role in ROLE_ORDER]

    @property
    def public_scenario_id(self) -> str:
        return CUSTOM_SCENARIO_ID_PREFIX + self.custom_scenario_id


def new_draft(segments_by_role: Mapping[str, str], title: str = "") -> CustomScenarioDraft:
    return CustomScenarioDraft(
        custom_scenario_id=uuid.uuid4().hex,
        title=title.strip() or DEFAULT_DRAFT_TITLE,
        segments_by_role=dict(segments_by_role),
        frozen=False,
    )


def validate_segments(segments_by_role: Mapping[str, str]) -> ValidationReport:
    """Validate a draft's segments for freeze-readiness.

    Distinct from `parse_pasted_scenario`'s report: this checks the
    *current* (possibly hand-edited) segment map held by a draft, not
    raw pasted text -- so its issue codes cover only what freezing
    actually requires (all seven known roles present, each non-empty).
    """

    issues: List[ValidationIssue] = []

    for role, text in segments_by_role.items():
        if role not in VALID_SEMANTIC_ROLES:
            issues.append(ValidationIssue("unknown_role", f"Unknown semantic role '{role}'."))

    for role in ROLE_ORDER:
        text = segments_by_role.get(role, "")
        if not text or not text.strip():
            issues.append(
                ValidationIssue(
                    "empty_segment_text",
                    f"Segment '{ROLE_LABELS[role]}' has empty text.",
                )
            )

    if len(segments_by_role) != len(ROLE_ORDER) or any(
        role not in segments_by_role for role in ROLE_ORDER
    ):
        issues.append(
            ValidationIssue(
                "invalid_segment_count",
                f"A custom scenario requires exactly {len(ROLE_ORDER)} segments, "
                "one per required semantic role.",
            )
        )

    return ValidationReport(tuple(issues))


def freeze_draft(draft: CustomScenarioDraft) -> ValidationReport:
    """Validate and, if valid, freeze ``draft`` in place.

    Returns the validation report either way -- the caller (the
    ``POST /api/custom-scenarios/{id}/freeze`` route) is responsible
    for surfacing it and for refusing to freeze an already-frozen
    draft *before* calling this (freezing is otherwise idempotent at
    the validation level, but re-freezing is treated as an error one
    layer up so editing-after-freeze is always caught explicitly).
    """

    report = validate_segments(draft.segments_by_role)
    if report.is_valid:
        draft.frozen = True
    return report


def to_scenario(draft: CustomScenarioDraft) -> Scenario:
    """Convert a frozen draft into the exact same `Scenario` model the
    built-in fixtures use, ready to hand to `ScenarioEngine`.

    Segment ids are generic and generated, not private/derived from
    any SAE identifier (e.g. ``custom_01_background_attachment``).
    Every segment is marked non-editable, matching the frozen-scenario
    invariant: once frozen, the exact text is replayed unchanged.
    """

    segments = tuple(
        ScenarioSegment(
            segment_id=f"custom_{index + 1:02d}_{role}",
            role=role,
            text=draft.segments_by_role[role],
            editable=False,
        )
        for index, role in enumerate(ROLE_ORDER)
    )
    return Scenario(
        scenario_id=draft.public_scenario_id,
        title=draft.title,
        description="A custom, user-supplied scenario created with the Scenario Wizard.",
        segments=segments,
        mode=MODE_FROZEN,
    )


def parse_public_scenario_id(scenario_id: str) -> Optional[str]:
    """Return the draft id encoded in a public scenario id, or ``None``.

    ``scenario_id`` is whatever a caller passed to the existing
    ``POST /api/runs``/``.../alternate`` flow -- for a built-in
    scenario this never matches (built-in ids never contain
    ``CUSTOM_SCENARIO_ID_PREFIX``), so this is a safe, additive check.
    """

    if scenario_id.startswith(CUSTOM_SCENARIO_ID_PREFIX):
        return scenario_id[len(CUSTOM_SCENARIO_ID_PREFIX) :]
    return None
