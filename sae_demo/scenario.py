"""Clean-room scenario schema for the SAE-DEMO backend scenario engine.

This is an independently designed, demo-specific representation. It is
not derived from, and does not reproduce, any private SAE Experiment 8
schema or protocol machinery — it exists only to describe an ordered,
segmented story for this demo's own engine.

Semantic role labels describe story *function* only (what narrative
job a segment plays), never private SAE memory structure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Tuple

MODE_FROZEN = "frozen"
MODE_INTERACTIVE = "interactive"
VALID_MODES = frozenset({MODE_FROZEN, MODE_INTERACTIVE})

# Generic semantic-role labels describing story function only. This set
# intentionally stays small and public-safe; it is meant to be reused by
# a future scenario generator, not to model any private memory schema.
VALID_SEMANTIC_ROLES = frozenset(
    {
        "background_attachment",
        "residual_possibility",
        "irreversibility",
        "neutral_event",
        "meaning",
        "relational_pressure",
        "closure",
    }
)


@dataclass(frozen=True)
class ScenarioSegment:
    """One ordered unit of a scenario.

    `role` is a free-form string at construction time so that a lenient
    loader (see `from_dict`) can build a segment from partial/malformed
    input and let `validate_scenario` report exactly what is wrong,
    rather than raising immediately.
    """

    segment_id: str
    role: str
    text: str
    editable: bool = True

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "role": self.role,
            "text": self.text,
            "editable": self.editable,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScenarioSegment":
        return cls(
            segment_id=str(data.get("segment_id", "")),
            role=str(data.get("role", "")),
            text=str(data.get("text", "")),
            editable=bool(data.get("editable", True)),
        )


@dataclass(frozen=True)
class Scenario:
    """An ordered, segmented demo scenario.

    `mode` is kept as a plain string (rather than coerced to an enum at
    construction time) so a malformed value can be reported by
    `validate_scenario` instead of raising during loading.
    """

    scenario_id: str
    title: str
    description: str
    segments: Tuple[ScenarioSegment, ...]
    mode: str

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "mode": self.mode,
            "segments": [segment.to_dict() for segment in self.segments],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Scenario":
        raw_segments = data.get("segments") or []
        segments = tuple(ScenarioSegment.from_dict(item) for item in raw_segments)
        return cls(
            scenario_id=str(data.get("scenario_id", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            segments=segments,
            mode=str(data.get("mode", "")),
        )

    def validate(self) -> "ValidationReport":
        return validate_scenario(self)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    issues: Tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return len(self.issues) == 0

    def codes(self) -> Tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


def validate_scenario(scenario: Scenario) -> ValidationReport:
    """Validate scenario structure and return every issue found.

    Deliberately collects *all* problems instead of failing on the
    first one, so a future Scenario Wizard UI can tell a user
    everything that needs fixing before a story is loaded.
    """

    issues: List[ValidationIssue] = []

    if not scenario.scenario_id.strip():
        issues.append(
            ValidationIssue("missing_scenario_id", "Scenario is missing a scenario_id.")
        )

    if not scenario.title.strip():
        issues.append(ValidationIssue("missing_title", "Scenario is missing a title."))

    if not scenario.segments:
        issues.append(ValidationIssue("no_segments", "Scenario has zero segments."))

    seen_segment_ids = set()
    for index, segment in enumerate(scenario.segments):
        label = segment.segment_id or f"<position {index}>"

        if not segment.segment_id.strip():
            issues.append(
                ValidationIssue(
                    "missing_segment_id",
                    f"Segment at position {index} is missing a segment_id.",
                )
            )
        elif segment.segment_id in seen_segment_ids:
            issues.append(
                ValidationIssue(
                    "duplicate_segment_id",
                    f"Segment id '{segment.segment_id}' is used more than once.",
                )
            )
        else:
            seen_segment_ids.add(segment.segment_id)

        if segment.role not in VALID_SEMANTIC_ROLES:
            issues.append(
                ValidationIssue(
                    "unknown_role",
                    f"Segment '{label}' uses unknown semantic role "
                    f"'{segment.role}'. Valid roles: {sorted(VALID_SEMANTIC_ROLES)}.",
                )
            )

        if not segment.text.strip():
            issues.append(
                ValidationIssue("empty_segment_text", f"Segment '{label}' has empty text.")
            )

    if scenario.mode not in VALID_MODES:
        issues.append(
            ValidationIssue(
                "invalid_mode",
                f"Scenario mode '{scenario.mode}' is not one of {sorted(VALID_MODES)}.",
            )
        )

    return ValidationReport(tuple(issues))


def scenario_to_json(scenario: Scenario) -> str:
    """Optional JSON export helper. No database/storage layer — this is
    purely a convenience for hand-authoring or inspecting a scenario."""

    return json.dumps(scenario.to_dict(), indent=2, sort_keys=True)


def scenario_from_json(json_text: str) -> Scenario:
    """Optional JSON import helper. See `scenario_to_json`."""

    return Scenario.from_dict(json.loads(json_text))
