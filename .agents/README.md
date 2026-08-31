# pylabjack agent knowledge base

Last source review: 2026-08-30

This directory holds durable repository context for maintainers and coding agents. `AGENTS.md` contains the mandatory working rules; files here explain the current implementation and why those rules exist.

Current baseline: uv library project, Python 3.11, `src/pylabjack` package layout, committed lockfile, and device-free pytest defaults.

## Index

- `project-context.md` — purpose, repository map, component ownership, lifecycle, and data flow.
- `thread-checkpoint.md` — rolling resume point and recovered decision timeline for the active long-running development thread.
- `workflows.md` — official uv commands, safe validation ladder, notebook policy, and remaining test/release requirements.
- `hardware-safety.md` — authorization boundary and the checklist for real LabJack access.
- `known-issues.md` — confirmed source-level defects, risks needing runtime confirmation, and missing infrastructure.
- `thread-history-incident.md` — evidence and mitigations for the 2026-08-30 Codex desktop history-rendering incident; this is tooling context, not a pylabjack defect.
- `export-codex-thread.ps1` — read-only recovery helper that renders user/assistant messages from a local Codex session log without exporting system, developer, reasoning, or tool records.

## Maintenance policy

- Repository continuity comes first. Treat the existing design philosophy, vocabulary, types, module boundaries, and semantics as constraints to understand and preserve before proposing a new abstraction.
- Search the implementation and its call sites before adding a type, enum, helper, or naming scheme. Reuse or extend the repository's established concept; do not create a parallel taxonomy for local convenience.
- Keep resource ownership explicit: the object that owns a resource provides its deterministic cleanup contract, while nested operation objects clean up only resources they start and never close a longer-lived owner implicitly.
- Record current behavior separately from desired behavior. Never describe a planned fix as implemented.
- Keep the public stream capability ledger (`docs/stream-capabilities.md`) and `_stream.py` module docstring synchronized with source, tests, safety boundaries, and known issues. Distinguish vendor capability, plan-only representation, calculation-only timing support, device-free validation, and hardware validation.
- Capture durable context as soon as it is confirmed; do not leave architecture, user decisions, support boundaries, validation evidence, or corrected assumptions only in conversation history.
- Keep `thread-checkpoint.md` short enough to read at every resume. Update the immediate next action and newly confirmed decisions, then move stable detail into the appropriate topic document instead of letting the checkpoint become a second project specification.
- If rendered conversation history is incomplete, recover from the local append-only session record with `export-codex-thread.ps1`; do not commit the raw log or paste system/developer/tool records into this knowledge base.
- Preserve user-authored comments and example flow. Public documentation, docstrings, comments, and demos describe how the current software behaves for a user; development history and agent reasoning belong in `AGENTS.md` or this knowledge base.
- When a user correction overturns an assumption, audit source, tests, README, and `.agents/` for consequences and remove the inaccurate account in the same change.
- Prefer stable references to a file and symbol over line numbers that will drift.
- Add an observation date when a fact depends on the local tool environment or external hardware.
- When resolving an issue, record the validating test or hardware procedure before removing it from `known-issues.md`.
- Update the repository map when files or responsibilities move, and update workflows when commands or dependencies become official.
- Do not store credentials, usable device identifiers, serial numbers, private paths, or raw measurement data here.
- Do not duplicate the full README. Public installation and usage belong in `README.md`; implementation context and agent guardrails belong here.
- Preserve undecided questions as open issues. Add an ADR under `.agents/decisions/` only when the project actually makes a durable architectural decision.
- In Markdown, write inline math as `$...$` and display math as `$$...$$`; do not use backslash-delimited TeX math markers.

For every substantive source change, review this index before implementation and again before handoff. Explicitly decide which documents need an update, and keep affected documents synchronized while the work evolves. If none do, leave them unchanged.
