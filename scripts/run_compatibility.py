"""Human-run CLI for the Memory-OFF synthetic compatibility runner.

Not part of the automated test suite and not intended to be executed
by an automated agent — it makes real, live Nebius/NVIDIA API calls
using whatever NEBIUS_API_KEY is configured in the local .env file,
and will incur provider usage.

This is a compatibility check, not a scientific experiment. It only
verifies that the target model can carry a scripted, multi-turn
synthetic scenario through the Nebius/NVIDIA provider with the
confirmed non-reasoning configuration — it draws no scientific
conclusions and supplies no Emotional Memory (Memory OFF only).

Usage (from the repository root):

    python scripts/run_compatibility.py --fixture greenhouse
    python scripts/run_compatibility.py --fixture new_studio
    python scripts/run_compatibility.py --fixture greenhouse --max-tokens 150

No fixture is hardcoded as a default — pick one explicitly with
--fixture so nothing needs to be edited in source to change it.
"""

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/run_compatibility.py` without
# installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from sae_demo.compatibility_runner import CompatibilityRunner, DEFAULT_MAX_TOKENS
from sae_demo.config import load_nebius_config
from sae_demo.nebius_provider import NebiusProvider
from sae_demo.scenario import MODE_FROZEN
from tests.fixtures.synthetic_scenarios import (
    build_benign_transition_fixture,
    build_irreversible_loss_fixture,
)

FIXTURES = {
    "greenhouse": build_irreversible_loss_fixture,
    "new_studio": build_benign_transition_fixture,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Memory-OFF synthetic compatibility harness: replays one "
            "built-in frozen synthetic fixture, segment by segment, "
            "through the live Nebius/NVIDIA provider."
        )
    )
    parser.add_argument(
        "--fixture",
        choices=sorted(FIXTURES),
        required=True,
        help="Which built-in synthetic frozen fixture to replay.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens per turn (default: {DEFAULT_MAX_TOKENS}).",
    )
    args = parser.parse_args()

    load_dotenv()
    config = load_nebius_config()
    provider = NebiusProvider(config)
    runner = CompatibilityRunner(
        provider, model_label=config.model, max_tokens=args.max_tokens
    )

    build_fixture = FIXTURES[args.fixture]
    scenario = build_fixture(mode=MODE_FROZEN)

    print(
        f"Compatibility check (Memory OFF only): '{scenario.title}' "
        f"[{args.fixture}] against {config.model}\n"
    )

    result = runner.run(scenario)

    for turn in result.turns:
        print(f"[{turn.segment_id}] role={turn.role}")
        print(f"  user:      {turn.user_text_sent!r}")
        if turn.error:
            print(f"  ERROR:     {turn.error}")
        else:
            print(f"  assistant: {turn.assistant_text!r}")
            print(
                f"  finish_reason={turn.finish_reason!r} "
                f"reasoning_present={turn.reasoning_present} "
                f"completion_tokens={turn.completion_tokens}"
            )
        print()

    print(f"Run completed: {result.completed}")
    if not result.completed:
        print("Run stopped early after a provider error — see the ERROR line above.")
    if any(turn.reasoning_present for turn in result.turns):
        print(
            "WARNING: at least one turn returned a non-null 'reasoning' field "
            "even though the non-reasoning configuration was sent."
        )


if __name__ == "__main__":
    main()
