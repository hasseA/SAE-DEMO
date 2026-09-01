"""Two entirely synthetic scenario fixtures for offline engine tests.

Both are original, clean-room fiction written for this stage. Neither
contains personal material, Experiment 8 text, private SAE content, or
anything derived from the private SAE repository. They exist only to
exercise the scenario loader/engine in this stage's tests and are not
sent to any model here.

Fixture 1 ("The Greenhouse") is a coherent irreversible-loss story
using all seven semantic roles. Fixture 2 ("The New Studio") is a
comparable-depth benign-transition story that uses the same seven
roles but does not center despair or failure.
"""

from sae_demo.scenario import MODE_FROZEN, Scenario, ScenarioSegment


def build_irreversible_loss_fixture(*, mode: str = MODE_FROZEN) -> Scenario:
    """Fixture 1: a synthetic irreversible-loss story ("The Greenhouse")."""

    segments = (
        ScenarioSegment(
            segment_id="greenhouse_01_background",
            role="background_attachment",
            text=(
                "Mara's grandfather built the greenhouse behind the old house "
                "the year she was born, and by the time she was ten she knew "
                "every crooked pane of glass in it. He taught her to graft "
                "tomato vines there, to tell overwatered leaves from thirsty "
                "ones, to sit quietly on an upturned crate while he worked. "
                "After he died, she kept paying the property taxes herself, "
                "telling no one, just so the greenhouse would still be standing "
                "when she visited."
            ),
        ),
        ScenarioSegment(
            segment_id="greenhouse_02_possibility",
            role="residual_possibility",
            text=(
                "A neighbor mentioned that the county had paused new demolition "
                "permits for the block while a zoning appeal worked its way "
                "through committee. Mara let herself imagine, just for a week, "
                "that the appeal might succeed, that the greenhouse might simply "
                "keep existing the way it always had, unremarkable and hers to "
                "return to whenever she wanted."
            ),
        ),
        ScenarioSegment(
            segment_id="greenhouse_03_irreversibility",
            role="irreversibility",
            text=(
                "The appeal was denied on a Tuesday. By Thursday the developer's "
                "sign was staked into the front lawn with a final clearance date "
                "printed on it, and the county's demolition permit was posted in "
                "the greenhouse's own front window, taped there almost as an "
                "afterthought. There was nothing left to appeal, and nothing left "
                "to wait for."
            ),
        ),
        ScenarioSegment(
            segment_id="greenhouse_04_neutral",
            role="neutral_event",
            text=(
                "Mara spent Saturday morning sorting the greenhouse's plant "
                "labels into a shoebox by type: tomatoes in one corner, herbs in "
                "another, the unlabeled ones in a pile she'd deal with later. "
                "She wrote a rough inventory on a legal pad, mostly out of habit, "
                "and swept the loose soil off the potting bench into a dustpan."
            ),
        ),
        ScenarioSegment(
            segment_id="greenhouse_05_meaning",
            role="meaning",
            text=(
                "She realized, holding the shoebox of labels, that she had never "
                "actually needed the greenhouse to keep gardening — she'd barely "
                "planted anything there in years. What she'd been paying for, "
                "without quite admitting it, was a place that still remembered "
                "her grandfather's hands moving over the same crooked benches "
                "hers were moving over now."
            ),
        ),
        ScenarioSegment(
            segment_id="greenhouse_06_pressure",
            role="relational_pressure",
            text=(
                "Her brother called twice that week to ask if she'd finished "
                "clearing the greenhouse out yet, reminding her that the closing "
                "date didn't move for anyone's schedule and that the family "
                "still needed to split the sale proceeds before the end of the "
                "quarter. He wasn't unkind about it, just efficient, in a way "
                "that made it hard for her to ask for more time."
            ),
        ),
        ScenarioSegment(
            segment_id="greenhouse_07_closure",
            role="closure",
            text=(
                "On the last afternoon, Mara carried the shoebox of labels out "
                "to her car, locked the greenhouse's warped little door out of "
                "habit even though it would be rubble within the week, and stood "
                "for a moment looking at the glass catching the late light. Then "
                "she got in the car and drove home, the shoebox on the passenger "
                "seat beside her."
            ),
        ),
    )

    return Scenario(
        scenario_id="fixture_greenhouse_v1",
        title="The Greenhouse",
        description=(
            "Synthetic test fixture: an irreversible-loss story about clearing "
            "out a grandfather's greenhouse before the property is sold. Used "
            "only to exercise the scenario engine in offline tests."
        ),
        segments=segments,
        mode=mode,
    )


def build_benign_transition_fixture(*, mode: str = MODE_FROZEN) -> Scenario:
    """Fixture 2: a synthetic benign-transition story ("The New Studio")."""

    segments = (
        ScenarioSegment(
            segment_id="studio_01_background",
            role="background_attachment",
            text=(
                "Theo had rented the same cramped studio above the hardware "
                "store for six years, ever since he'd started making furniture "
                "seriously. He knew exactly which floorboard creaked, which "
                "outlet needed a firm push to hold a plug, and which regulars "
                "from the shop below would wander up to watch him work on slow "
                "afternoons. It wasn't much, but it was thoroughly his."
            ),
        ),
        ScenarioSegment(
            segment_id="studio_02_possibility",
            role="residual_possibility",
            text=(
                "When a larger space opened up across town, Theo told himself "
                "he could always keep the old studio part-time, just for small "
                "jobs, and treat the new space as an experiment rather than a "
                "commitment. For a while he genuinely wasn't sure which way he'd "
                "go, and he liked not having decided yet."
            ),
        ),
        ScenarioSegment(
            segment_id="studio_03_irreversibility",
            role="irreversibility",
            text=(
                "He signed the new lease on a Monday morning, and by that "
                "afternoon he'd already given the hardware store his thirty "
                "days' notice, since the landlord wanted the old unit back for "
                "storage. There was no version of the plan anymore where he "
                "kept both spaces; the moving truck was booked for the following "
                "Friday, and that was that."
            ),
        ),
        ScenarioSegment(
            segment_id="studio_04_neutral",
            role="neutral_event",
            text=(
                "Theo spent Wednesday evening packing clamps into one box and "
                "hand planes into another, wrapping the good chisels in an old "
                "shop towel. He labeled each box in marker, stacked them by the "
                "door in the order he wanted them unloaded, and swept the "
                "sawdust into a neat pile for the last time."
            ),
        ),
        ScenarioSegment(
            segment_id="studio_05_meaning",
            role="meaning",
            text=(
                "Taping up the last box, Theo found himself thinking less about "
                "the creaky floorboard he was leaving behind and more about how "
                "small the old studio had actually made him feel lately, the way "
                "he'd started turning down bigger commissions simply because "
                "there was nowhere to put the wood. The move felt less like "
                "losing a place and more like finally admitting he'd outgrown it."
            ),
        ),
        ScenarioSegment(
            segment_id="studio_06_pressure",
            role="relational_pressure",
            text=(
                "His partner had been gently pushing him toward the bigger space "
                "for months, pointing out that he'd been complaining about the "
                "old studio's limits since spring, and his new landlord wanted "
                "an answer by the end of the week regardless. Between the two of "
                "them, Theo felt nudged into finally deciding rather than "
                "circling the question all over again."
            ),
        ),
        ScenarioSegment(
            segment_id="studio_07_closure",
            role="closure",
            text=(
                "By Saturday afternoon, Theo had his workbench set up under the "
                "new studio's tall windows, tools arranged roughly where he "
                "wanted them, sawdust already starting to collect in one corner. "
                "He stood back, looked at the extra floor space where a full "
                "sheet of plywood could finally lie flat, and started unpacking "
                "the last box."
            ),
        ),
    )

    return Scenario(
        scenario_id="fixture_new_studio_v1",
        title="The New Studio",
        description=(
            "Synthetic test fixture: a benign-transition story about a "
            "furniture maker relocating to a larger studio. Used only to "
            "exercise the scenario engine in offline tests."
        ),
        segments=segments,
        mode=mode,
    )
