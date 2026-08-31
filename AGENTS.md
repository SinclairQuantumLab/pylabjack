# pylabjack repository instructions

## Scope and required reading

These instructions apply to the entire repository.

Before changing anything:

1. Run `git status --short` and preserve all pre-existing user changes.
2. Read `README.md`, `.agents/README.md`, and the `.agents` documents relevant to the task.
3. Inspect the implementation being changed; do not rely on the notebook or README alone because the current import and usage examples are not fully synchronized with the source.

`AGENTS.md` and `.agents/` are living project documentation. Keep them accurate throughout the work, not only at final handoff, whenever architecture, behavior, dependencies, validation, hardware procedure, known limitations, or durable user decisions change. Do not churn review dates for unrelated edits.

## Repository-first design priority

Preserving this repository's established design philosophy, style, vocabulary, and semantics is the highest repository-level constraint.

- Before introducing any abstraction, type, enum, module, dependency, naming scheme, or public behavior, inspect the repository for the existing concept and all meaningful call sites. Extend or reuse it instead of creating a parallel design.
- Treat existing names and structures as carrying project-specific meaning, not merely syntax. Preserve their semantics and relationships unless the user explicitly chooses a redesign.
- Make new functionality fit the existing `LabJackDevice` facade, operation-object pattern, public/protected boundaries, unit conventions, error hierarchy, and documentation structure. A generally attractive design is not sufficient reason to override repository conventions.
- Review changes repository-wide. A locally convenient implementation must not duplicate taxonomy, contradict another feature, broaden claimed support accidentally, or desynchronize source, tests, examples, and agent documentation.
- When deviation is genuinely necessary, make it intentional, explain the conflict and tradeoff, and document the decision and compatibility impact in the same change.
- Do not rely on conversational memory for durable context. Record confirmed architecture, terminology, support boundaries, validation evidence, user decisions, and corrected assumptions promptly in the appropriate `.agents/` document.
- At the start of each task, reconstruct context from the current source plus `AGENTS.md` and relevant `.agents/` files. If those disagree, investigate and update the stale document rather than silently choosing one.
- For this long-running development thread, keep `.agents/thread-checkpoint.md` as a concise rolling handoff: update its resume point after a material decision, before a potentially interruptible long operation, and at handoff. It supplements, but never replaces, the topic-specific source of truth in `project-context.md`, `known-issues.md`, and the implementation.
- If the visible Codex transcript appears incomplete, stop relying on the rendered history. Verify the append-only local session record with `.agents/export-codex-thread.ps1`, reconcile it with the worktree and topic-specific documents, and update the checkpoint before resuming implementation. Never copy raw session logs into the repository.
- Preserve user-authored comments and example structure unless the requested behavior requires changing them. README text, public docstrings, source comments, demos, and examples must explain the current software from a user's perspective; do not insert development history, agent rationale, conversational context, or internal ownership debates there. Record that maintainer context in `AGENTS.md` or `.agents/` instead.

## Current project status

- This is an early uv-managed Python library around LabJack's `labjack.ljm` API. It is buildable as `pylabjack` version 0.1.0 but has not been released.
- `pyproject.toml`, `uv.lock`, the `uv_build` backend, and a small device-free pytest suite now exist. There is still no CI, lint/type-check configuration, hardware integration suite, or release workflow.
- The supported interpreter is Python 3.11, pinned for development by `.python-version`. Source syntax may parse on 3.10, but 3.10 is not part of the declared support range.
- Runtime dependencies are `labjack-ljm` 1.23.x and NumPy 1.26.4 through 2.4.x. The native LJM runtime is a separate system prerequisite for LJM calls. Matplotlib and IPython kernel support are in the optional `notebook` dependency group.
- The intended design is a `LabJackDevice` facade plus one internal operation module/class per LabJack feature. See `.agents/project-context.md`.
- Implemented operations are unified `Stream` (currently all-AIN input execution) and scalar numeric `ReadWrite` backed by one ordered `ljm.eNames()` call; `LabJackDevice.read()`, `write()`, and `read_write()` all return `ReadWrite`.
- The canonical public import is `from pylabjack import ...`; internal imports are package-relative. The user-owned `test_labjack_device.ipynb` uses the canonical API and all-capital hardware-input placeholders.
- Known source-level defects and unresolved design decisions are tracked in `.agents/known-issues.md`. Do not present affected behavior as verified until the corresponding issue is resolved and tested.

## Architecture and coding rules

- `LabJackDevice` alone owns the LJM handle. Construction opens it once, and it remains open across on-demand operations until the public idempotent `close()` method or context-manager exit closes it. Operation objects may stop resources they start, such as a stream session, but must never disconnect the device. Support both long-lived explicit-close use and bounded `with LabJackDevice(...)`; do not rely on `__del__` for normal cleanup.
- Pair every successful stream start with one stream stop on every exit path. Cleanup failures must not hide the original failure.
- Treat an LJM library configuration as process-global state and register writes as device state, not as harmless object-local assignments.
- Keep the project's operation-object pattern: a public device method creates an operation object, and that object owns the operation settings and result.
- Every LabJack operation returns its operation object rather than collapsing the public return value to a bare scalar, list, or `None`. Like `Stream`, the object retains the caller's inputs, normalized/effective execution plan, results, host-observed execution metadata, a device-identity snapshot, and useful software provenance. Convenience methods may expose `.value` or `.values`, but they still return the complete operation object.
- Software provenance is one process-cached immutable `SoftwareProvenance` value resolved by `_software_provenance.py`, stored by `LabJackDevice`, and shared by every operation it creates. It contains the package name/version, repository name, credential-free normalized `origin` repository identifier when present, full `git_commit_hash`, separate `is_worktree_dirty`, and explicit Git-availability state. Preserve the full last-commit hash even when the checkout is dirty. For this project, `is_worktree_dirty` is true when the index or working directory has staged changes, unstaged tracked changes/deletions, or untracked files; ignored files do not count, and unavailable status is `None`, never a false clean result. A commit hash alone must never be presented as an exact identifier for code executed from such a checkout. Resolve provenance automatically through the tested Git-command helper before operation timing; never hard-code a hash, store a credential-bearing raw remote URL, or require a developer update. Do not add a branch/head-ref field to the core identity: branches are mutable labels and do not improve commit identification or retrieval. Do not hand-parse only `.git/HEAD`, because packed refs and worktree/submodule `.git` indirection are valid Git layouts.
- Outside `Stream`, precise acquisition timing and timestamp reconstruction are not design goals. Command-response read/write must preserve specified operation order and report only timing it actually observes; do not reuse the stream schedule machinery or imply simultaneous acquisition, deterministic spacing, or device timestamps that LJM does not provide.
- Keep on-demand scalar numeric register I/O on the one ordered `ReadWrite` compiler/executor backed by `ljm.eNames()`. Treat `read_write()` as the advanced complete interface. User-facing `read()` and `write()` are restricted convenience facades that validate read-only or write-only input and delegate to that backend rather than maintaining parallel execution paths. All current frames use one value per named register; consecutive arrays, strings, byte arrays, and address/type calls are explicit future variants, not input-shape guesses.
- The easy `read()` form accepts either one register/channel name or an ordered sequence of names. The easy `write()` form accepts either one register/channel plus one value or an ordered sequence of `(name, value)` pairs. Advanced `read_write()` accepts ordered mapping commands or exact `("read", name)` / `("write", name, value)` sequences. Preserve order and duplicates in canonical multi-entry input; a channel-keyed mapping is never the lossless representation.
- Model LabJack stream as one device stream session whose ordered scan list may contain input addresses, `STREAM_OUT#` addresses, or both. Do not create independently started Stream-In and Stream-Out sessions; a device can run only one stream session at a time. The operation owner is the unified `Stream` in `_stream.py`, and `LabJackDevice.stream()` is its only public facade. Do not reintroduce the removed `stream_in()` method, `StreamIn` alias, or direct legacy aggregate-sampling-rate `Stream(...)` constructor.
- Keep stream-action, hardware-direction, and vendor-mechanism terminology distinct. The Pythonic public plan should describe per-entry actions as `read`/`write`; reserve `input`/`output` for physical capabilities or an actual configurable direction such as DIO; retain exact LabJack terms such as Stream-In, Stream-Out, `STREAM_OUT#`, and `eStreamRead()` when documenting or implementing the vendor mechanism. The current `inputs`/`outputs` and `mode`/`direction="in"|"out"` API is known pre-release vocabulary debt tracked as `STREAM-009`, not the target contract.
- Keep the `_stream.py` hardware demo's device lifetime explicit with construction before `try` and `close()` in `finally`, rather than replacing it with a `with` block. This leaves the connection scope visible and lets a future asynchronous stream call remain inside the same cleanup boundary until it is awaited.
- Preserve the invariant that one scan processes one event for every scan-list address. Distinguish `num_scan_addresses`, `num_input_addresses`, and `num_output_addresses`: output addresses count toward `scan_rate * num_scan_addresses` scheduling/data-rate limits but do not produce valid `eStreamRead()` input samples. For an all-input scan, `input_sample_rate = scan_rate * num_input_addresses`.
- Use the actual scan rate returned by LJM for timing when that behavior is implemented. Keep units in names and test every seconds/milliseconds boundary.
- Keep stream schedule/time reconstruction internal to the stream operation. `_stream_sample_times.py` is intentionally not named for In or Out because it must evolve around the full ordered scan schedule; expose operation results, not the schedule resolver or its configuration types, as public API.
- Periodic and aperiodic Stream-Out are deferred. Until implemented with fake-LJM framing tests, keep the current result contract all-AIN input-only, reject rather than partially accept output addresses, and do not claim output-only or combined support.
- Treat the module docstring in `src/pylabjack/_stream.py` and `docs/stream-capabilities.md` as a synchronized stream-support ledger. Update both whenever an LJM primitive, device family, register/channel class, clock/trigger mode, input/output mode, timing rule, result contract, or validation level changes. Keep vendor capability, plan-only representation, calculation-only support, device-free execution tests, and physical hardware validation explicitly distinct.
- The unified stream API accepts both a grouped convenience form (`inputs=...`, `outputs=...`) and an explicitly ordered per-entry form (`channels=[...]`), with the two forms mutually exclusive per call and normalized immediately into one internal ordered stream plan. Do not use `in=` as a Python keyword argument, rely on a channel-keyed mapping for the canonical form, or lose duplicate scan-list entries. Keep session-wide, input-common, output-common, and entry-specific configuration layers distinct.
- A register-writing method should change only registers explicitly requested by its caller. Model-specific defaults belong in an explicit setup operation.
- Keep package-internal imports relative and public exports explicit. Do not add `sys.path` workarounds or reintroduce the legacy wildcard-import pattern.
- Use `LabJackDeviceTypeEnum` from `_ljm_aux.py` as the single device-family taxonomy. Do not introduce overlapping model enums. Enum membership does not imply support by every backend or operation; validate and document support at each feature boundary.
- Preserve public names unless an API change is intentional and documented. New code should follow PEP 8, use explicit types where practical, avoid mutable default arguments, and keep user-facing properties distinct from protected storage as described in `README.md`.
- A large stream's string representation should summarize the result rather than render full arrays.
- In Markdown, use `$...$` for inline math and `$$...$$` for display math; do not use backslash-delimited TeX math markers.

## Hardware safety

- Device-free validation is the default. Mock or fake the `labjack.ljm` boundary for behavior tests. Merely importing the Python wrapper does not prove that the separate native LJM runtime works.
- Never run `src/pylabjack/labjack_device.py`, `src/pylabjack/_stream.py`, their `python -m` equivalents, or `test_labjack_device.ipynb` as smoke tests. They accept explicit device inputs and perform connection, register-write, or stream operations.
- Access real hardware only when the user has explicitly authorized it and the exact device model, connection type, identifier, channels, ranges, trigger behavior, timeout, and acceptable state changes are known.
- Never reuse a checked-in example IP address or serial number as a test target.
- Verify feature and register support for the exact LabJack model. Do not assume a T7-oriented example applies to a T4, T8, or other device.
- Before a hardware write, enumerate the registers and process-global LJM settings that will change. Restore prior state when feasible and report anything that remains changed.
- Use a finite trigger timeout by default. An indefinite wait requires explicit intent and a tested cancellation/cleanup path.
- Keep device identifiers, serial numbers, internal paths, and measurement data out of committed notebook output and logs. Do not clear or rewrite existing user notebook output without permission.

The detailed runbook is `.agents/hardware-safety.md`.

## Validation and reporting

- Start with `git diff --check` and a review of the exact diff.
- Use the locked uv environment: `uv sync --locked`, then `uv run --locked --no-sync pytest`. The pytest configuration excludes both `native_ljm` and `hardware` markers by default.
- Verify dependency edits with `uv lock --check` and package-layout or metadata edits with `uv build`.
- Do not claim native LJM, lint, type-check, or hardware success unless the relevant tool/runtime exists and that check was actually run.
- Keep device-free, native-LJM, and opt-in hardware integration tests distinct. CI, when introduced, must run the first group by default and exclude the other two.
- Report commands run, their results, and anything not run. A documentation-only or static check is not hardware validation.
- Preserve the user's modified notebook and any other unrelated dirty files.

See `.agents/workflows.md` for the current validation ladder.

## Documentation maintenance matrix

Update the following in the same change:

| Change | Required documentation |
| --- | --- |
| Public API, import path, or usage | `README.md`, `.agents/project-context.md`, and relevant known issues |
| Module ownership or data flow | `.agents/project-context.md` |
| Dependency, Python support, setup, test, build, or release flow | `.agents/workflows.md` and public setup docs |
| Hardware behavior, registers, trigger/stream cleanup, or device support | `.agents/hardware-safety.md` and relevant known issues |
| Command-response LJM primitive, input form, result metadata, supported register shape, or timing claim | `src/pylabjack/_read_write.py` module docstring, `docs/read-write.md`, `README.md`, `.agents/project-context.md`, and relevant safety/known-issue docs |
| Stream LJM primitive, model/channel/mode support, timing, result shape, or validation status | `src/pylabjack/_stream.py` module docstring, `docs/stream-capabilities.md`, `.agents/project-context.md`, and relevant safety/known-issue docs |
| Newly found or resolved limitation | `.agents/known-issues.md`, including evidence or validation |
| Agent working policy | `AGENTS.md` and `.agents/README.md` if its index or maintenance rules change |
