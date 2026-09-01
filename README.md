# SAE-DEMO

A standalone Nebius hackathon project demonstrating SAE (Stable Emotion) Emotional Memory concepts against an NVIDIA model hosted through Nebius.

## Status

Planning stage only. No application code exists yet. This commit initializes project structure and specification documents; implementation has not begun.

## What this project is

A small, independently built demo that lets a user compare an NVIDIA model's responses to a fixed scenario with an existing, bounded Emotional Memory representation supplied ("Memory ON") against the same scenario without it ("Memory OFF"), alongside a compact evidence card summarizing a conservative, already-published scientific result and a labeled conceptual visualization of the Emotional Memory idea.

## What this project is not

This is not the SAE research codebase, and it does not create, extract, or freeze Emotional Memory. It consumes one already-existing, bounded Emotional Memory export as an opaque external input. See `docs/DISCLOSURE_BOUNDARY.md` for what may and may not enter this repository, and `docs/PRODUCT_SPEC.md` / `docs/ARCHITECTURE.md` for the product and architecture this project targets.

## Relationship to the private SAE repository

SAE-DEMO is a clean-room project, independently implemented. It is not a fork, clone, filtered export, or copy of the private SAE research repository. Nothing in this repository was copied from that repository; where this repository needs to describe a concept from that research, it is described independently, in this project's own words.

## Documents

- `docs/PRODUCT_SPEC.md` — product purpose, user flow, MVP scope, explicit non-goals
- `docs/ARCHITECTURE.md` — component-level architecture for the independent demo
- `docs/DISCLOSURE_BOUNDARY.md` — short operational rules for what may/may not enter this repository
