# SAE-DEMO Architecture (planning-level)

Status: planning only. No component below has been implemented. This document describes the independent-demo-level shape of the system, not a schema or an implementation plan.

## Scope of this document

Components are described only at the level needed to reason about the public/private disclosure boundary and to plan Stage-4-and-later implementation work. No file formats, APIs, or internal data shapes are fixed here. In particular, the bounded demo Emotional Memory export's exact structure is explicitly not defined in this document — see "The bounded artifact is opaque" below.

## Memory OFF path

```
User
  -> SAE-DEMO UI
  -> Demo conversation controller
  -> Nebius/NVIDIA provider adapter
  -> target NVIDIA model (via Nebius)
```

The user's scenario is sent to the target model with no Emotional Memory context. This is the baseline path and the simpler of the two.

## Memory ON path

```
Bounded demo artifact (supplied from outside this project)
  -> independent demo consumer
  -> conversation context
  -> Demo conversation controller
  -> Nebius/NVIDIA provider adapter
  -> target NVIDIA model (via Nebius)
```

The same user scenario is sent alongside content derived from the bounded demo artifact. The demo consumer's only job is to load the artifact and fold it into the conversation context in some form; it does not evaluate, score, select among, or weight parts of the artifact based on the scenario — no recognition or activation step exists in this path.

## Components

**SAE-DEMO UI.** The chat interface, Memory OFF/ON comparison view, Scenario Builder, conceptual visualization panel, Recognition/Activation prototype panel (if included), and Experiment 8 evidence card. Independently built; no SAE UI exists to build from (the private repository has none).

**Demo conversation controller.** Owns one scenario run: sends the Memory OFF request, sends the Memory ON request, and holds both results for side-by-side display. Independently built, deliberately simple — it does not need SAE's experiment-lifecycle state machine, authorization gating, or provenance machinery, none of which are appropriate for a live hackathon demo and none of which cross the disclosure boundary into this repository.

**Nebius/NVIDIA provider adapter.** Translates the controller's request into a call against the selected NVIDIA model hosted through Nebius, using a user-supplied API key held locally, never persisted server-side or committed. Independently built against Nebius's own published interface; not derived from or modeled on any SAE provider-adapter code.

**Independent demo consumer.** Loads the bounded demo Emotional Memory export and produces whatever text/content is added to the Memory ON conversation context. Built entirely independently of `v2_lifecycle.py`, `v2_emotional_injections.py`, `v2_emotional_networks.py`, the private `data/v2/` stores, and the private XNET/XINJ validation machinery — none of that code, or logic derived from it, is used here. This component does not know, and does not need to know, how the underlying Emotional Memory was originally derived, extracted, or frozen.

**Conceptual visualization components.** Render the Emotional Memory concept chain and, if included, the proposed Recognition/Activation direction, using only demo-safe, illustrative, synthetic content — never real Emotional Memory structure, weights, labels, or payload content. The Recognition/Activation panel, if built, is visually and textually marked "Prototype / Conceptual" wherever it appears, and never implies Experiment 8 demonstrated those mechanisms.

**Experiment 8 evidence card.** A static UI element presenting only the frozen conservative public claim (see `docs/PRODUCT_SPEC.md`). No dynamic data, no linked transcripts, no internal IDs.

## The bounded artifact is opaque

The bounded demo Emotional Memory export is treated by every component in this repository as an opaque external input: some file or payload supplied from outside this project, in a format this document does not define. SAE-DEMO's demo consumer knows how to load and use that bounded export; it does not, and must not, contain or reconstruct the private procedure that created or froze the underlying Emotional Memory. Designing that export's exact format, contents, and provenance is a separate, later product-design decision and is out of scope for this document and this stage.

## Explicitly not part of this architecture

No component in this repository implements Emotional Memory creation, extraction, XNET generation, XINJ generation, the private XNET/XINJ schema, recognition, activation, model-specific alignment/fine-tuning, or an A/B/C scientific replication runner. Where the demo needs to gesture at these ideas (the conceptual visualization, the Recognition/Activation prototype panel), it does so illustratively and labels the boundary between demonstrated and proposed explicitly.
