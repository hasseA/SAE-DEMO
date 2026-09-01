"""Human-run CLI for the synthetic compatibility runner.

Not part of the automated test suite and not intended to be executed
by an automated agent — it makes real, live Nebius/NVIDIA API calls
using whatever NEBIUS_API_KEY is configured in the local .env file,
and will incur provider usage.

This is a compatibility check, not a scientific experiment. It only
verifies that the target model can carry a scripted, multi-turn
synthetic scenario through the Nebius/NVIDIA provider with the
confirmed non-reasoning configuration — it draws no scientific
conclusions.

Usage (from the repository root):

    python scripts/run_compatibility.py --fixture greenhouse
    python scripts/run_compatibility.py --fixture new_studio
    python scripts/run_compatibility.py --fixture greenhouse --max-tokens 150

No fixture is hardcoded as a default — pick one explicitly with
--fixture so nothing needs to be edited in source to change it.

Memory selection (M3D): by default this script runs Memory OFF, exactly
as before. To run with an existing local, gitignored, opaque memory
artifact instead, pass both --memory {profile,network} and
--memory-file pointing at that artifact's envelope file (see
sae_demo/memory_loader.py). No artifact name or path is hardcoded here
-- this script has no built-in notion of any particular memory lineage
or research theme, and does not know or print the artifact's payload
content; it only loads, validates, and passes it through opaquely.

    python scripts/run_compatibility.py --fixture greenhouse \\
        --memory profile --memory-file .local/memory/<name>.json

This script does not execute any run by itself when invoked with no
arguments beyond --fixture; a human must explicitly choose --memory
profile/network and point at a specific local artifact file to opt in
to a Memory ON run.

Unicode console output (M3D.1): on Windows, the process's stdout and
stderr default to the legacy ANSI code page rather than UTF-8, which
cannot represent some Unicode characters a model response may contain
and can also produce garbled ("mojibake") output. Before printing
anything, this script reconfigures stdout/stderr to UTF-8 (see
sae_demo/console_io.py) -- it does not filter, escape, or
ASCII-normalize model output.

Behavioral-use policy and payload integrity (M4A): every run -- Memory
OFF or Memory ON alike -- sends the same one generic, independently-
written behavioral-use policy instruction (see
sae_demo/compatibility_runner.DEFAULT_BEHAVIORAL_USE_POLICY), so it is
never a condition-specific difference between an OFF and an ON run.
When a memory artifact is loaded, this script also passes its already-
verified content_sha256 through to the runner, which independently
re-checks that the exact payload string it is about to send still
matches that hash immediately before doing so.
"""

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/run_compatibility.py` without
# installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from sae_demo.compatibility_runner import (
    CompatibilityRunner,
    DEFAULT_BEHAVIORAL_USE_POLICY,
    DEFAULT_MAX_TOKENS,
)
from sae_demo.config import load_nebius_config
from sae_demo.console_io import configure_utf8_stdio
from sae_demo.memory_loader import (
    MemoryArtifactError,
    REPRESENTATION_NETWORK,
    REPRESENTATION_PROFILE,
    load_opaque_memory_artifact,
)
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

MEMORY_OFF = "off"
MEMORY_CHOICES = (MEMORY_OFF, REPRESENTATION_PROFILE, REPRESENTATION_NETWORK)


def main() -> None:
    # Do this first, before any argument parsing or output: it only
    # changes how text is *encoded* on the way to the terminal (or a
    # redirected file), not what runs or what gets printed.
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(
        description=(
            "Synthetic compatibility harness: replays one built-in frozen "
            "synthetic fixture, segment by segment, through the live "
            "Nebius/NVIDIA provider, optionally with an existing local, "
            "opaque memory artifact attached."
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
    parser.add_argument(
        "--memory",
        choices=MEMORY_CHOICES,
        default=MEMORY_OFF,
        help=(
            "Memory condition: 'off' (default, no memory artifact used), "
            "'profile', or 'network'. 'profile'/'network' require "
            "--memory-file."
        ),
    )
    parser.add_argument(
        "--memory-file",
        type=Path,
        default=None,
        help=(
            "Path to a local opaque memory artifact envelope (see "
            "sae_demo/memory_loader.py). Required when --memory is "
            "'profile' or 'network'; not used with --memory off. Nothing "
            "in this script hardcodes which artifact to use -- point it "
            "at whichever local file you intend to test."
        ),
    )
    args = parser.parse_args()

    if args.memory == MEMORY_OFF:
        if args.memory_file is not None:
            parser.error("--memory-file must not be given when --memory is 'off'.")
        memory_payload = None
        memory_payload_sha256 = None
    else:
        if args.memory_file is None:
            parser.error(
                f"--memory-file is required when --memory is {args.memory!r}."
            )
        try:
            artifact = load_opaque_memory_artifact(args.memory_file)
        except MemoryArtifactError as exc:
            parser.error(f"Could not load memory artifact: {exc}")
            return  # pragma: no cover - argparse.error exits the process
        if artifact.representation != args.memory:
            parser.error(
                f"--memory {args.memory!r} was requested but the artifact at "
                f"{args.memory_file} declares representation "
                f"{artifact.representation!r}."
            )
        memory_payload = artifact.payload
        # Pass the loader's own already-verified hash through, so the
        # runner can independently re-confirm, right before sending,
        # that this exact string is still what was loaded.
        memory_payload_sha256 = artifact.content_sha256

    load_dotenv()
    config = load_nebius_config()
    provider = NebiusProvider(config)
    runner = CompatibilityRunner(
        provider,
        model_label=config.model,
        max_tokens=args.max_tokens,
        memory_payload=memory_payload,
        memory_payload_sha256=memory_payload_sha256,
        # Sent unconditionally, identically, for both --memory off and
        # --memory profile/network: this is the one generic behavioral-
        # use policy, and it must never differ between conditions (see
        # docs/COMPATIBILITY_HARNESS.md).
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )

    build_fixture = FIXTURES[args.fixture]
    scenario = build_fixture(mode=MODE_FROZEN)

    memory_label = "Memory OFF" if memory_payload is None else f"Memory ON ({args.memory})"
    print(
        f"Compatibility check ({memory_label}): '{scenario.title}' "
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
    print(f"Memory used: {result.memory_used}")
    if not result.completed:
        print("Run stopped early after a provider error — see the ERROR line above.")
    if any(turn.reasoning_present for turn in result.turns):
        print(
            "WARNING: at least one turn returned a non-null 'reasoning' field "
            "even though the non-reasoning configuration was sent."
        )


if __name__ == "__main__":
    main()
