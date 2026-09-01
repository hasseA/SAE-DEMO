"""Manual, human-run smoke test for the Nebius/NVIDIA provider.

Not part of the automated test suite and not intended to be executed
by an automated agent — it makes a real, live API call using whatever
NEBIUS_API_KEY is configured in the local .env file, and will incur
provider usage.

Run it yourself from the repository root:

    python scripts/smoke_nebius.py
"""

import sys
from pathlib import Path

# Allow running as `python scripts/smoke_nebius.py` without installing
# the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from sae_demo.config import load_nebius_config
from sae_demo.nebius_provider import NebiusProvider


def main() -> None:
    load_dotenv()
    config = load_nebius_config()
    provider = NebiusProvider(config)

    result = provider.complete(
        [{"role": "user", "content": "Reply exactly with: SAE-DEMO API TEST OK"}],
        max_tokens=100,
    )

    print(f"content:            {result.content!r}")
    print(f"reasoning:          {result.reasoning!r}")
    print(f"finish_reason:      {result.finish_reason!r}")
    print(f"completion_tokens:  {result.completion_tokens!r}")

    if result.reasoning_warning:
        print(
            "\nWARNING: the response included a non-null 'reasoning' field "
            "even though the non-reasoning configuration was sent. The "
            "Nebius endpoint or model may have changed behavior."
        )


if __name__ == "__main__":
    main()
