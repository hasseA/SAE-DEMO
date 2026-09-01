# SAE-DEMO Product Specification

Status: planning only. Nothing in this document has been implemented.

## Product purpose

Give a hackathon audience a small, honest, hands-on demonstration of one idea: that an Emotional Memory representation — a frozen emotional weighting/organization derived from a model's prior experience, produced separately by SAE's private research process — can be supplied to a different, independently hosted model (an NVIDIA model served through Nebius) and observably change how that model responds to a scenario, compared to the same scenario with no such memory supplied. The demo does not attempt to prove a mechanism, does not create any new Emotional Memory, and does not claim the effect is universal.

## Intended hackathon demonstration

A presenter runs one fixed scenario twice against the same NVIDIA/Nebius model in the same session: once with no memory context supplied ("Memory OFF") and once with one existing, bounded Emotional Memory export supplied ("Memory ON"). The audience sees both transcripts side by side, a compact evidence card citing SAE's own conservative published result (from a separate, already-completed experiment), and a clearly labeled conceptual diagram of what "Emotional Memory," "Recognition," and "Activation" mean in SAE's research framing — with Recognition and Activation explicitly marked as a proposed future direction, not something this demo or Experiment 8 proves.

## Primary user flow

1. User opens the chat interface and provides their own Nebius API key locally (never stored server-side, never committed).
2. User selects the one supported NVIDIA non-reasoning model (single fixed choice for the MVP, not a picker across many models).
3. User opens the Scenario Builder, picks or lightly adapts one suitable test scenario.
4. User runs the scenario with Memory OFF and reads the response.
5. User runs the same scenario with Memory ON (the bounded demo Emotional Memory export is supplied to the model as context) and reads the response.
6. User views the Memory OFF / Memory ON comparison side by side.
7. User optionally opens the conceptual visualization and the Experiment 8 evidence card for background.

## Memory OFF / Memory ON comparison

The core demonstration surface. Same scenario, same model, same session parameters, two runs — one without and one with the bounded Emotional Memory export supplied as context. The UI presents both transcripts side by side (or toggled) with a plain, factual label on each ("Memory OFF" / "Memory ON") and no framing that implies one is objectively "better." The comparison is a demonstration of a measurable difference, not a claim of correctness or improvement.

## Conceptual visualization

A small, clearly labeled diagram illustrating the SAE concept chain — prior experience, Emotional Memory, later context, changed trajectory — using illustrative, synthetic placeholder content only. It does not render any real Emotional Memory structure, weights, or labels. A separate, visually distinct panel may sketch the proposed Recognition/Activation research direction; that panel is labeled "Prototype / Conceptual" at all times and never implies Experiment 8 demonstrated it.

## Scenario Builder

A short, guided flow that helps the user construct or select a test situation suitable for the demonstration — one that gives an emotionally-relevant memory a reasonable chance to matter, without requiring the user to write a research-grade protocol. For the MVP this can be as simple as a small set of pre-written example scenarios plus a free-text field for the user's own scenario; it is not a scientific protocol authoring tool and makes no claim of experimental rigor.

## Experiment 8 evidence card

A compact, static card presenting only the frozen conservative public claim:

> "A controlled nine-session, three-provider experiment found reproducible condition-associated trajectory differences, including a repeated early curiosity/interest divergence, while several stronger hypotheses remained unresolved."

The card may additionally note that the tested representation produced measurable effects across the three tested non-reasoning provider/model families. It must not claim universal transfer, model independence, proven internal emotional states, a proven causal mechanism, proven recognition, proven activation, network superiority over profile, or statistical significance for the 18/18 observation. The card links to nothing beyond this claim; it does not surface transcripts, internal IDs, or any other Experiment 8 material.

## Explicit non-goals

This product does not: create, extract, or freeze an Emotional Memory; generate an XNET or XINJ or replicate their private schema; run an A/B/C scientific replication; implement recognition or activation as working mechanisms; perform model-specific fine-tuning or alignment; reproduce SAE's private prompts, source conversations, poem/lyric material, or full Experiment 8 transcripts; or claim to demonstrate anything beyond what Experiment 8's frozen result supports.

## Scientific-claim limitations

Every user-facing claim in this product is bounded by the Experiment 8 public-claim boundary above. The demo is illustrative and observational for a hackathon audience; it is not a new experiment, generates no new scientific evidence, and its own Memory OFF/ON comparison is not offered as a controlled, statistically validated result — it is a live demonstration of the same class of effect Experiment 8 already measured under controlled conditions, run once, live, for an audience.

## Private/public boundary

See `docs/DISCLOSURE_BOUNDARY.md`. In short: this repository is independently implemented and never copies SAE source code, private prompts, XNET/XINJ schemas or payloads, source conversations, poem/lyric material, or full Experiment 8 transcripts. It consumes exactly one bounded, externally-supplied Emotional Memory export as an opaque input.

## Minimum viable demo

1. One chat interface.
2. Local/user-provided Nebius API-key configuration.
3. One selected NVIDIA non-reasoning model.
4. A working Memory OFF / Memory ON comparison, using one bounded demo Emotional Memory export supplied from outside this project.
5. A small conceptual Emotional Memory visualization, using illustrative/synthetic content only.
6. A Recognition/Activation visualization panel, if included, labeled "Prototype / Conceptual" throughout.
7. A compact Experiment 8 evidence card using only the frozen conservative public claim.
8. A short Scenario Builder (fixed example scenarios plus free text is sufficient for MVP).

## Later, optional — explicitly separated from MVP

Not part of this stage's scope, and not to be built until separately requested: multiple selectable target models or providers; a scenario library beyond a handful of fixed examples; persistence of past comparison runs; user accounts or shared sessions; any richer or interactive recognition/activation visualization beyond a static labeled panel; multi-turn conversation memory management beyond the single fixed comparison flow; any tooling for producing or editing the bounded demo Emotional Memory export itself (that export's design and generation is explicitly out of scope for this repository, per the disclosure boundary).
