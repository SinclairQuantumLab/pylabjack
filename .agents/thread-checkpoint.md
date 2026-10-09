# Current development-thread checkpoint

Last updated: 2026-10-09

This file is the rolling handoff for the long-running `developing pylabjack`
thread. It exists because the Codex desktop client has rendered incomplete
history for this thread more than once. Stable project facts still belong in
the implementation and the topic-specific documents indexed by
`.agents/README.md`.

## Resume here

The uv environment/refreshed lockfile, notebook template policy, notebook
examples/exit cleanup, and README are now separate local `develop` commits
(2026-10-09). This handoff records the associated agent guidance and validation.
The local notebook and its outputs are preserved. The user's latest ignore
rule is `test_*.ipynb`; the regenerated lockfile also updates notebook/development
dependencies within the existing declared ranges. Runtime dependency
declarations and Python support are unchanged. No push or merge into `main`
was performed. Validation remains static/diff-only; no tests or hardware runs.

Both notebooks now import `atexit` and register the bound `lj_device.close`
method immediately after successful connection (2026-10-09). This is a
normal-Python-exit fallback; existing explicit close remains. Notebook-tab
closure, cell interruption, and forced termination are not covered, and known
stream completion/cleanup issues remain open. Existing local device values
and saved outputs are preserved. Validation is static only; no tests or
hardware execution.

Also synchronized the latest local plot edits into the template: 10-by-4
figures, multi-channel alpha 0.5, a title derived from `READ_CHANNELS`, removal
of the multi-read array print and the empty code cell. Local output is retained.

Added one consecutive multi-register read/plot cell after the local single-read
examples in both notebooks (2026-10-09): ten ordered `read()` calls for the
user-selected AIN0/AIN1/AIN2, plotted against reading index with one legend
entry per channel. Also synchronized the user's pyplot import, operation-type
print, and consecutive single-register read/plot cells into the template.
Existing local cells and outputs are preserved; template device/register/write
inputs retain placeholders and all outputs/counts remain empty. Only static
syntax/preservation review and diff hygiene; no tests or hardware execution.

`INPUT_CHANNELS` was moved from connection to the stream execution cell in
both notebooks (2026-10-09). Connection requires only device selection;
operation-specific settings belong with the corresponding example. Local
channel values and all other cells, metadata, and saved outputs were preserved.
This is an example-only edit: static preservation review and diff hygiene,
with no tests or notebook/hardware execution.

The README's original high-level code-style emphasis and PEP 8 guidance were
restored verbatim directly under `Developer's note` (2026-10-09). They are the
introduction before its subsections; the detailed `Code style` subsection
remains. Preserve this content when reorganizing documentation, as now recorded
in `AGENTS.md` and the agent index. Documentation-only diff review and
`git diff --check` are sufficient; no tests or hardware execution.

Single-register read and write examples were added to both the template and
the existing local notebook at the user's request (2026-10-09), immediately
after connection and before streaming. They retain the operation objects and
show `.value` for reads and `.written_values` for requested writes, explicitly
not readback. Register names and the numeric write value require placeholder
replacement. Existing local cells, device selection, and saved outputs are
preserved; neither notebook is executed. No library behavior changed.

The user requested ongoing notebook-to-template maintenance (2026-10-09).
At each development task, inspect the ignored local notebook's code and
Markdown and propagate reusable edits to the tracked template, preserving
template setup instructions and hardware placeholders. Never copy local
device values, saved output, execution counts, or private metadata, and leave
the local working copy untouched. This policy is task-time review, not a
background watcher. The current connection-cell edit now assigns enum objects
to configuration variables and passes them directly to `LabJackDevice` in
the template as well. Validation is limited to static review and diff hygiene;
no notebook execution, tests, or hardware access is needed.

Routine uv commands are now plain `uv sync`, `uv lock`, and `uv run`
(2026-10-09). Both `dev` and `notebook` are configured as default uv groups:
one `uv sync` prepares pytest, Jupyter kernel support, and plotting as well as
the library. The expected initial workflow uses the notebook, so do not
require a separate `--group notebook` command. Keep Python
support, dependency groups/ranges, build metadata, the development interpreter,
the generated lockfile, and setup documentation consistent. Current Python
3.11 selection, project version, runtime requirements, and dependency groups
were compared with lock metadata and agree. Historical command records remain
unchanged. No dependency upgrade or support-range change was requested.
Plain `uv lock` and `uv sync` succeeded without changing `uv.lock`, using the
existing writable temporary cache. Diff checks passed; no tests or builds ran.

After adding `notebook` to the default groups, `uv lock` still succeeds with
no lockfile change. The updated `uv sync` selected the notebook dependencies;
downloads succeeded outside the network-restricted sandbox, but installation
stopped on access denied while replacing `.venv` package metadata. Do not claim
the local notebook environment is installed. No environment repair, pytest,
or standalone package build was attempted.

The README is now organized for users (2026-10-09): installation, connection,
register operations, streaming/results, notebook use, provenance, and support
limits. Contributor setup, tests/builds, implementation guidance, module demos,
and code style are subsections under `Developer's note`. Keep this audience
boundary in future edits; it is recorded in `AGENTS.md` and the agent index.
Existing operation examples and comments were retained. No library behavior
changed; this documentation-only task uses diff review and `git diff --check`,
with no tests, builds, or hardware execution.

The first development task adopts the notebook convention confirmed in
`SinclairQuantumLab/py-siglent-spd3000` on 2026-10-09: commit
`test_labjack_device.ipynb.template`, copy it to the ignored local
`test_labjack_device.ipynb`, and preserve existing local inputs and outputs.
The current user-edited ignore rule covers `test_*.ipynb` working copies;
`*.ipynb.template` files remain eligible for Git tracking.
The original local file is retained unchanged; the template adds only copy
instructions. README, agent context, safety/workflow guidance, and the existing
static test path are synchronized. Validation is limited to diff review and
Git ignore verification; no tests, build, notebook, or hardware execution.
No library behavior has changed and no next feature has been selected.

The user has set a lightweight validation policy (2026-10-09): simple tasks
may skip tests; behavior changes should use only useful focused checks; creating
or running comprehensive tests requires explicit user approval after explaining
the reason, scope, and expected overhead. The full pytest suite is not an
automatic step, including during repository orientation. This decision is
recorded in `AGENTS.md` and `workflows.md`, with the agent index and public
testing guidance synchronized. This policy-only change was checked by diff
review and `git diff --check`; no tests were added or run.

The receiving thread has now reviewed the repository at the user's request to
understand the project first. The starting worktree was clean at `b400a7b`.
README, agent context, implementation, capability docs, and tests confirm the
existing operation-object contracts and deferred features below. No next
feature or redesign has been selected; await the user's next development task.
No implementation or notebook changes were made during this orientation.

Validation on 2026-10-09: locked environment sync succeeded using a writable
temporary uv cache. The device-free suite passed all 122 tests on Python
3.11.16 after running outside the sandbox's temporary-directory permission
restriction, with pytest's cache provider disabled. Earlier sandboxed runs
passed 113 tests but could not set up nine temporary-path fixtures.
`git diff --check` passed. No build, native-LJM, or hardware check was run.

### Previous transfer context (2026-08-30)

The user ended the affected thread after another visible-history omission and
requested a commit suitable for transfer to a new thread, agent, or computer.
Treat the handoff commit containing this file as the authoritative starting
point. Do not redo the uv migration, unified-stream cleanup, provenance work,
or scalar command-response implementation merely because the new transcript
does not show their development history.

The shared provenance foundation and on-demand scalar numeric register I/O are
implemented. The next step should begin from these current contracts:

- `_software_provenance.py` is a standalone standard-library-only resolver.
  `LabJackDevice` captures one cached immutable package/Git snapshot before
  connecting; `ReadWrite`, `Stream`, and every future operation share it.
- Branch/head-ref is deliberately absent. Repository name, credential-free
  normalized `origin`, full commit hash, dirty state, and explicit Git
  availability provide the core source identity.
- `read_write()` is the complete advanced command-response interface;
  `read()` and `write()` are restricted facades over the same `ReadWrite` /
  `ljm.eNames()` backend. All return the complete operation object.
- Easy reads accept one name or an ordered sequence. Easy writes accept one
  name/value or an ordered sequence of pairs. Advanced mixed commands accept
  ordered mappings or exact compact read/write sequences. Order and duplicates
  are preserved.
- `ReadWrite` retains the defensive original request, immutable normalized
  commands/results, effective LJM arrays, `.value`/`.values`/
  `.written_values`, whole-call host timing, immutable device identity, and
  software provenance.
- Precise timing outside `Stream` remains out of scope. Command-response reads
  have no reconstructed per-frame timestamps, simultaneity, or deterministic
  spacing claim.
- Numeric arrays, strings, byte arrays, and address/type register calls remain
  explicit specialized variants. Decide their API before implementing them;
  do not infer them from scalar input shape or present them as Stream sampling.

The transfer is intended to leave the complete uv/src-layout migration and
subsequent stream/lifecycle/provenance/read-write work committed together and
the worktree clean. If a receiving checkout is dirty, inspect and preserve its
changes rather than assuming they are generated by this handoff. After
provenance and scalar command-response I/O were added, the locked device-free
suite passed all 122 tests and wheel/sdist builds on 2026-08-30. Pytest warned
that its cache directory was not writable, but that did not affect collection
or results. The installed Python wrapper was inspected, but the native LJM DLL
was unavailable; no physical hardware validation has been performed.

No further feature was selected after scalar `ReadWrite` was completed. The
receiving agent should first run `git status --short`, read `AGENTS.md`, this
file, `project-context.md`, and `known-issues.md`, then confirm the user's next
priority. The main known choices are intentionally unresolved: specialized
array/string/byte/address register variants (`RW-002`), the pre-release stream
`input`/`output` to `read`/`write` vocabulary refactor (`STREAM-009`), and the
stream execution/cleanup defects listed as `STREAM-001`, `STREAM-002`, and
`STREAM-004`. None should be inferred as authorized merely from its position
in that list.

## Recovered decision timeline

### Project foundation

- Maintain `AGENTS.md` and `.agents/` as living context, and keep durable
  decisions out of conversational memory alone.
- The repository was converted into an early uv-managed Python 3.11 library
  with a `src/pylabjack` layout, lockfile, build metadata, and device-free
  pytest defaults.
- Preserving the repository's established design philosophy, naming, style,
  vocabulary, and semantics is the highest repository-level design rule.
  Extend existing concepts after repository-wide inspection instead of adding
  parallel abstractions.
- Public docs, docstrings, comments, and examples must speak to software users.
  Development history and maintainer rationale belong here under `.agents/`.

### Stream timing and timestamps

- `scan_rate` is the repetition rate of the complete ordered scan list. Each
  scan-list position has an acquisition/update offset inside that scan, so
  per-channel spacing is one scan period while channels within a scan are not
  generally simultaneous.
- LabJack timing tables were treated as predetermined schedules, not evidence
  of a real-time adaptive settling controller. Scheduled time does not promise
  that the analog input has settled accurately for an arbitrary source.
- Internal sample-time reconstruction uses the actual rate returned by
  `eStreamStart()` and the ordered acquisition schedule. T4/T7 use documented
  auto-settling regions, T8 AIN inputs are simultaneous, and U-family timing is
  calculation-only support where the manuals permit it.
- The resolver remains private. Users consume times through the `Stream`
  result; README gives only a short mention and links the detailed document.
- `_stream_sample_times.py` intentionally has neither `in` nor `out` in its
  name because it must evolve around the full stream schedule.
- Markdown math uses `$...$` and `$$...$$`.

### Repository taxonomy and settling guidance

- `LabJackDeviceTypeEnum` is the single model taxonomy. U3, U6, UE9, and U12
  belong there even though enum membership does not imply that every operation
  supports every model. A parallel stream-model enum was removed.
- Stream settling advice is preflight guidance derived only from configured
  settings and published tables. It does not accept or infer source
  resistance; the user interprets the compact source-resistance thresholds.
- T-Series stream uses the scan-list-wide `STREAM_SETTLING_US`; per-channel
  `AINn_SETTLING_US` belongs to command-response acquisition.
- The compact message begins directly with `INFO:` or `WARNING:` and lists
  threshold/value points on one line. General multiline tagged messages indent
  continuations by the exact tag-prefix width.

### Unified stream model and current support boundary

- A device has one stream session. Stream-In and Stream-Out are not separate
  independently started sessions; one ordered scan list may eventually carry
  input addresses, `STREAM_OUT#` addresses, or both.
- `Stream` in `_stream.py` owns that session, and `LabJackDevice.stream()` is
  the only public facade. The pre-release `stream_in()` method, `StreamIn`
  alias, aggregate-rate conversion helper, and direct legacy constructor have
  been removed and must not be reintroduced.
- The public plan accepts mutually exclusive grouped `inputs`/`outputs` and an
  explicitly ordered `channels` form. It separates session-wide,
  direction-common, and entry-specific configuration and preserves duplicate
  entries in the plan.
- The current `in`/`out` vocabulary conflates stream action, physical channel
  direction, and LabJack's Stream-In/Stream-Out mechanism. The planned
  pre-release correction uses public stream actions `read`/`write` (grouped
  `read`/`write`, ordered `action`, `read_config`/`write_config`), reserves
  `input`/`output` for physical capability or actual DIO direction, and keeps
  exact vendor terms such as Stream-Out, `STREAM_OUT#`, and `eStreamRead()`.
  This is recorded as `STREAM-009` and is not implemented yet.
- Periodic and aperiodic Stream-Out execution are deferred. The current
  executor remains all-AIN input-only and rejects output plans before device
  configuration. The capability ledger is the `_stream.py` module docstring
  plus `docs/stream-capabilities.md`.

### Device and example lifecycle

- `LabJackDevice` alone owns the LJM handle. Construction opens once; explicit
  idempotent `close()` or context exit closes it. Long-lived on-demand use and
  bounded `with LabJackDevice(...)` use are both supported.
- An operation stops only resources it starts. `Stream` pairs stream start/stop
  but never disconnects the device.
- The stream demo intentionally constructs the device before `try` and closes
  it in `finally`, retaining a visible connection scope suitable for a future
  awaited asynchronous stream call. Preserve user-authored example comments
  and flow unless behavior requires a change.
- Hardware demos accept device type, connection type, and device identifier as
  explicit positional inputs. The stream demo fixes ordinary demo channels and
  acquisition settings; hardware paths are never automated smoke tests.

### Command-response I/O selection

- LJM `*Array` calls address consecutive registers in the register map; they do
  not mean repeated time-spaced samples and are not a substitute for Stream.
- `eReadNames()`/`eWriteNames()` are homogeneous multi-register calls.
  `eNames()` is the generalized ordered mixed read/write primitive and is the
  implemented backend for pylabjack's complete scalar command-response
  operation.
- “Single-time” means on-demand command-response, not single-channel and not
  simultaneous acquisition.

## Recovery procedure

1. Read `AGENTS.md`, this checkpoint, the relevant topic documents, and the
   exact source/diff before continuing.
2. If the rendered transcript conflicts with this checkpoint, use
   `export-codex-thread.ps1` against the local rollout JSONL and inspect the
   user/assistant record. The script deliberately omits privileged and tool
   records.
3. Reconcile recovered decisions with source and topic documents. Source is
   authoritative for implemented behavior; planned behavior must remain
   explicitly marked as planned.
4. Update the resume section after the next material decision or implementation
   handoff. Never commit a raw Codex session log.

For this transfer, the helper recovered 259 user/assistant message records
through the user's commit-and-transfer request from the append-only rollout
log. The raw export was used only for reconciliation and was not added to the
repository.
