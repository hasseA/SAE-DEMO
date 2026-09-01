# SAE-DEMO Disclosure Boundary (operational summary)

This is a short, independent operational summary for developers working in this repository. The controlling document is the private SAE repository's `docs/decisions/SAE_HACKATHON_IP_DISCLOSURE_BOUNDARY.md` (commit `b313148acd25d96b0bcba48de54b983720a20438`), which is not reproduced here and is not part of this repository. If this summary and that document ever appear to conflict, treat the private document as authoritative and raise the discrepancy before proceeding — do not resolve it by editing this file to match your best guess.

## The one rule

This repository is built independently. Nothing is copied, ported, translated, or "cleaned up" from the private SAE research repository (`C:\Projects\SAE`) into this one. The private repository may be *read* by a developer for understanding, terminology, or scientific facts. It may not be a source of files, code, prompts, schemas, or data for this repository.

## Never enters this repository

- SAE source code of any kind (Python modules, prompt strings, validation logic, schemas)
- The private XNET or XINJ schema, structure, or field layout
- Any actual XNET or XINJ payload, in whole or in part
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

## When in doubt

If it's unclear whether something may enter this repository, stop and raise it rather than including it. This file is a summary for day-to-day development, not a substitute for the private repository's controlling disclosure document.
