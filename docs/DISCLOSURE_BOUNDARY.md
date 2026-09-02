# SAE-DEMO Disclosure Boundary (operational summary)

This is a short, independent operational summary for developers working in this repository. The controlling documents are the private SAE repository's `docs/decisions/SAE_HACKATHON_IP_DISCLOSURE_BOUNDARY.md` (M2) and `docs/decisions/SAE_HACKATHON_PROFILE_MEMORY_DISCLOSURE_DECISION.md` (M2.1, which narrowly supersedes specific M2 clauses for one named, validated artifact only), neither of which is reproduced here and neither of which is part of this repository. If this summary and those documents ever appear to conflict, treat the private documents as authoritative and raise the discrepancy before proceeding — do not resolve it by editing this file to match your best guess.

## The one rule

This repository is built independently. Nothing is copied, ported, translated, or "cleaned up" from the private SAE research repository (`C:\Projects\SAE`) into this one. The private repository may be *read* by a developer for understanding, terminology, or scientific facts. It may not be a source of files, code, prompts, schemas, or data for this repository.

## Never enters this repository

- SAE source code of any kind (Python modules, prompt strings, validation logic, schemas)
- The private XNET or XINJ schema, structure, or field layout — except as embodied in the one specific approved profile Emotional Memory artifact described under "Profile Emotional Memory release status" below
- Any actual XNET or XINJ payload, in whole or in part — except that one specific, named, already-validated profile Emotional Memory export (see below); this does not extend to any other artifact, including the network-representation export
- Source emotional conversations or any transcript from which Emotional Memory was derived
- Private poem/lyric material
- Full Experiment 8 transcripts
- The private Frame measurement prompt/instrument
- Any Emotional Memory extraction, creation, freezing, or A/B/C replication logic
- Any recognition or activation algorithm or formula
- Any model-specific fine-tuning/alignment method
- Private scientific/provenance IDs, unless a specific one is genuinely required and has been explicitly cleared
- Any API key, credential, or secret

## May enter this repository

- Independently written application code (UI, conversation handling, provider adapters, configuration, logging)
- The conservative, already-published Experiment 8 public claim, quoted verbatim and not strengthened
- Independently authored, conceptual descriptions of Emotional Memory, Recognition, and Activation, clearly distinguishing what has been demonstrated from what is a proposed future direction
- Illustrative, synthetic-data visualizations of the Emotional Memory concept and of proposed recognition/activation behavior, the latter always labeled "Prototype / Conceptual"
- A consumer for one bounded, externally-supplied Emotional Memory export, treated as an opaque input whose internal format this project does not need to know or replicate from the private schema
- The one specific, already-validated profile-representation Emotional Memory artifact named under "Profile Emotional Memory release status" below, including its existing weights, meanings, classifications, schema/field names, wrapper, and consumption framing, exactly as approved by the private repository's M2.1 decision

## Profile Emotional Memory release status (M2.1)

The private repository's M2.1 decision (`docs/decisions/SAE_HACKATHON_PROFILE_MEMORY_DISCLOSURE_DECISION.md`) approved, in principle, the public distribution of one specific, already-validated Emotional Memory export: the profile-representation artifact identified there by its envelope `content_sha256` (`ad659ae31004d3f54c0d96fbcb74f374d5674b75f37ff6ff0c3dacf545a9c1e2`). That approval covers the artifact's existing content, weights, meanings, classifications, schema/field names, wrapper, and consumption framing exactly as they already exist — this repository must not sanitize, rename, rewrite, summarize, or otherwise transform that artifact before or as part of distributing it.

The corresponding network-representation artifact (`content_sha256` `0ede24bf907b6c409751ff8cc4df4ed6e0888563b9ef80fae19841722d51f330`) is explicitly **not** covered by this approval and remains local-only/private under the rule below, pending a separate decision.

This status change affects only which artifact may be distributed and how it may be described. It does not change anything about how this repository's code treats a memory artifact (still loaded and forwarded as an opaque string — see `sae_demo/memory_loader.py`), and it does not disclose, and must never be used to justify disclosing, how SAE creates, extracts, derives, weights, or freezes an Emotional Memory. That creation methodology remains private without qualification.

As of this release-packaging stage, the approved artifact is additionally distributed as a tracked file at `demo_memory/despair_profile.json` (byte-identical to the artifact named above) so that a fresh clone can run Memory ON without any access to the developer's local machine. See `docs/RUNTIME_DATA_BOUNDARY.md` for how this tracked copy relates to the still-local-only `.local/memory/` directory.

## Runtime data (M3C.1)

**Nothing originating from private SAE is Git-tracked in SAE-DEMO by default.** This applies to source material covered above and, separately, to this project's own runtime output: live run traces, provider responses, generated scenario drafts, and any future bounded Emotional Memory artifact are local-only by default, under the gitignored `.local/` root. See `docs/RUNTIME_DATA_BOUNDARY.md` for the full local/tracked split, how the one approved tracked exception is scoped, and how the boundary is checked before a commit.

## When in doubt

If it's unclear whether something may enter this repository, stop and raise it rather than including it. This file is a summary for day-to-day development, not a substitute for the private repository's controlling disclosure document.
