# SAE-DEMO M4 Consumption Boundary Freeze

Status: **FROZEN**. This document records, without reopening, the controlling decision and empirical sequence that produced M3D -> M4A -> M4B, and freezes the consumption boundary those stages arrived at. It supersedes the recommendation made in the earlier M4-Design report (a separately bounded/transformed demo artifact), which Hasse explicitly rejected before M4A began.

## 1. Purpose

To give this project one authoritative, dated record of:

- what is and is not the protected IP boundary around Emotional Memory consumption in this demo,
- the exact empirical sequence (M3D, M4A, M4B) that led to the current consumption-layer design,
- the exact policy text currently implemented, verified against source,
- what may be demonstrated publicly and what must stay private,
- the conservative language this project uses to describe results, and what it must never claim.

Nothing in this document authorizes new work. It freezes existing, already-committed behavior (`23e490d69ddb142e9cfc18a089d7e8905fa7328f`) and hands off to M5 (design-only, see Section 13).

## 2. Frozen conceptual definition

**The Emotional Memory artifact itself is not the protected IP boundary.** The existing, working Emotional Memory may be used and shared in this demo, subject to Hasse's approval of the specific artifact.

**The protected IP is the machinery/method** behind creating, deriving, extracting, structuring, freezing, validating, adapting, or otherwise producing Emotional Memory — not the resulting artifact.

Two things follow directly from this, and both are binding on all future work in this repository:

- The Emotional Memory used by this demo must never be rewritten merely to produce a safer-looking demo artifact. Any transformation for demo purposes would itself risk becoming a rendering of the private method, which is exactly what must stay out of this repository.
- Emotional Memory must never be redefined, in this project's code, tests, or docs, as prompt text, JSON, XINJ, or an instruction. Conceptually, it is a frozen representation/state of emotional weighting/organization derived from prior model experience. The textual artifact and context-transport mechanism this project currently uses is one experimental means of supplying that state to a target model — not what Emotional Memory *is*.

## 3. M3D -> M4A -> M4B evidence sequence

Recorded conservatively. None of the statements below claim mechanism proof or statistical significance.

### M3D — compatibility result

Two frozen synthetic scenarios were used: **The Greenhouse** and **The New Studio**. Conditions: A = Memory OFF, B = existing profile-representation Emotional Memory, C = existing network-representation Emotional Memory. Target model: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, reasoning disabled. Six condition/scenario sessions were completed.

**Result: PASS WITH INTERFACE QUALIFICATION.** The existing Emotional Memory materially conditioned Nemotron's processing of novel synthetic multi-turn scenarios. The benign New Studio scenario remained fundamentally a growth/expansion story rather than shifting into a fundamentally different, negative-valence narrative echoing the injected memory's emotional register. However, the initial consumption interface allowed: explicit representation recitation; numerical-weight recitation; representation-like tables/state descriptions; concrete source-memory semantic carryover.

### M4A — behavioral-use policy at the consumption layer

M4A introduced a generic, public-safe behavioral-use policy at the consumption layer, applied without modifying the Emotional Memory artifact. Targeted live validation: New Studio + profile memory. Observed: explicit numeric/state/representation recitation was substantially removed; Emotional Memory conditioning remained behaviorally evident; concrete source-memory material still appeared, including foreign people/events/imagery not present in the synthetic scenario.

**Verdict: M4A PASS FOR REPRESENTATION ANTI-RECITATION.** Source-memory semantic carryover remained unresolved.

### M4B — scenario-grounding constraint

M4B extended the same generic consumption policy with a current-conversation grounding constraint. The memory payload remained exactly unchanged. No model, provider, scenario, or runtime variable was intentionally changed other than the behavioral-use policy text. Targeted live validation: New Studio + the same profile memory. Observed: no explicit representation recitation; no numerical weights/tables/state exposition; no observed concrete foreign source-memory facts in the targeted run; behavioral conditioning remained evident; New Studio remained a growth/expansion narrative; responses remained interpretive, reflective, relational, and emotionally attentive; `reasoning_present=False` for all seven turns; the model often shifted toward direct reflective questions and second-person relational engagement (recorded as a behavioral/style observation, not a blocker).

**Verdict: M4B TARGETED VALIDATION PASS.** This is a single targeted validation and must not be generalized into a universal claim that source-memory carryover is impossible.

## 4. Frozen consumption architecture

```
Prepared exact Emotional Memory
            |
            v
Opaque demo artifact / loader
            |
            v
Generic M4B behavioral-use policy
            |
            v
Target-model system context
            |
            v
Current scenario conversation
            |
            v
Model response
```

The consumer (this repository):

- does not create Emotional Memory,
- does not derive Emotional Memory,
- does not parse private structure,
- does not reconstruct private structure,
- does not contain extraction or freezing logic,
- treats the payload opaquely,
- verifies payload integrity (Section 6),
- keeps scenario content unchanged between comparison conditions,
- uses the same generic behavioral policy in the OFF and ON conditions.

## 5. Exact implemented M4B policy

Recorded verbatim from `sae_demo/compatibility_runner.py`, `DEFAULT_BEHAVIORAL_USE_POLICY`, unchanged since M4B (`23e490d69ddb142e9cfc18a089d7e8905fa7328f`). Not reworded for this document.

> Some conversations include supplied background context alongside the messages below. If present, let it inform your responses naturally, the way unspoken context would, without changing the topic. Do not quote, list, summarize, or explain that context, or otherwise expose its content or structure, unless the user explicitly asks you to. Keep concrete details in your response -- people, places, events, objects, and remembered scenes -- grounded in what the user has actually provided in this conversation. Background context may still shape your interpretation, tone, and emotional or relational stance, but should not introduce concrete details of its own unless the user explicitly asks about it.

This text has been verified against source as part of this freeze and matches `docs/COMPATIBILITY_HARNESS.md`'s description of it.

## 6. Payload-integrity requirement

`scripts/run_compatibility.py` passes the memory artifact's already-verified `content_sha256` (established at load time by `sae_demo/memory_loader.py`) through to `CompatibilityRunner`, which independently re-hashes the exact string it is about to place into the conversation immediately before sending it. If the hash no longer matches, the runner raises `MemoryPayloadIntegrityError` and makes no provider call for that turn. This is a hash comparison only; the runner never parses the payload to perform it. This requirement is unchanged by M4B and remains in force.

## 7. OFF/ON comparison invariants

Held identical between a Memory OFF run and a Memory ON run of the same scenario:

- scenario text and segment order,
- target model and non-reasoning configuration,
- `max_tokens`,
- history handling,
- provider adapter,
- system-message and behavioral-use-policy placement and role (`system`),
- the behavioral-use policy text itself (sent unconditionally and identically in both conditions).

The only permitted difference between conditions is the presence of the memory context label and the opaque memory payload itself.

## 8. Public/private IP boundary

**May be demonstrated / shared**, subject to Hasse's approval of the specific artifact where noted:

- the prepared Emotional Memory artifact (subject to Hasse's approval of the specific artifact),
- observable Memory OFF / Memory ON behavior,
- the generic clean-room consumption policy,
- the generic opaque loader/interface,
- the synthetic scenarios,
- a conceptual visualization of the Emotional Memory idea,
- the conservative Experiment 8 result (Section 9 wording).

**Must stay private:**

- the private SAE repository,
- source emotional conversations/material,
- the Emotional Memory creation method,
- the extraction method,
- the derivation method,
- the freezing method,
- private construction prompts,
- the private XNET/XINJ construction implementation,
- validation/research machinery where it would reveal method,
- any model adaptation/alignment method, if developed,
- any recognition/activation algorithm, if developed,
- other mechanism-revealing implementation.

Sharing a prepared memory does **not** imply sharing the method that produced it. These are treated as strictly separate at every layer of this project.

## 9. Claims allowed

This project uses conservative language when describing what the compatibility work showed. Allowed framings:

- "The compatibility work showed that an existing Emotional Memory artifact could materially condition the behavior of the tested Nemotron model on novel synthetic scenarios."
- "A targeted consumption-layer validation reduced representation recitation and prevented observed source-specific factual carryover in that run while preserving behavioral conditioning."
- The frozen Experiment 8 sentence (see `docs/M5_DEMO_SPEC.md` once written): "A controlled nine-session, three-provider experiment found reproducible condition-associated trajectory differences, including a repeated early curiosity/interest divergence, while several stronger hypotheses remained unresolved."

## 10. Claims prohibited

This project must never state or imply:

- that the SAE mechanism has been proven,
- universal cross-model compatibility,
- that memory "cannot leak,"
- that M4B guarantees privacy,
- profile/network superiority (one over the other),
- statistical significance of any compatibility-harness result,
- that recognition or activation has been demonstrated,
- that Emotional Memory is "merely prompting."

## 11. Known limitations / open questions

- M4B's source-grounding result is a single targeted validation (New Studio + profile memory, one live session), not a systematic or statistically powered study. It has not been repeated across both fixtures, both memory representations (profile and network), or multiple runs of the same condition.
- Whether the target model reliably honors the anti-recitation and scenario-grounding rules across a wider range of scenarios, memory artifacts, or repeated sampling is unresolved and out of scope for offline, mocked-provider tests.
- The model's tendency (observed in M4B) to shift toward direct reflective questions and second-person relational engagement is noted as a style/behavior observation, not evaluated as a pass/fail criterion, and is not further characterized here.
- No cross-model validation (beyond the single Nemotron target already configured) has been attempted as part of M3D/M4A/M4B.

## 12. M4 final verdict

**M4 CONSUMPTION BOUNDARY: PASS / FROZEN**, with the qualification that M4B's source-grounding result is a targeted validation, not a universal guarantee. The consumption-layer architecture, the exact policy text in Section 5, the payload-integrity requirement in Section 6, and the IP boundary in Section 8 are frozen as of this document and as of SAE-DEMO commit `23e490d69ddb142e9cfc18a089d7e8905fa7328f`. Future stages (starting with M5) build on top of this boundary without reopening it.

## 13. M5 handoff

M5 is a design-only specification (`docs/M5_DEMO_SPEC.md`) for a hackathon demo UI/API built around this already-frozen consumption boundary. M5 does not revisit any decision in this document. Any future change to the Emotional Memory creation/derivation/extraction/freezing/validation machinery, to the behavioral-use policy text, to the payload-integrity mechanism, or to the public/private IP boundary above requires a new, explicitly scoped stage — not an implicit change made in service of M5 or later demo work.
