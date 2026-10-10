# Development and validation workflows

Last workflow review: 2026-10-09

## Official uv baseline

The repository is a uv-managed library with an `uv_build` backend, `src/pylabjack` package, committed `uv.lock`, and Python 3.11 development pin. Use uv rather than global `pip` or an activated external environment.

```powershell
# Default project environment (runtime + dev + notebook groups).
uv sync

# Focused device-free test, when useful. The environment is already synchronized.
uv run pytest tests/test_read_write.py -k test_read_one

# Full device-free suite, only when explicitly requested or approved.
uv run pytest

# Regenerate the lockfile when dependency declarations change.
uv lock

# Build the source distribution and wheel.
uv build

```

`uv.lock` is committed and must change with dependency metadata. The `dev` group contains pytest and the `notebook` group contains ipykernel and Matplotlib. Both are configured in `[tool.uv].default-groups`, so plain `uv sync` prepares the complete expected project environment, including notebook use. The project supports Python `>=3.11,<3.12`; `.python-version` selects 3.11 and uv may install a managed interpreter.

User installation and contributor setup both use `uv sync`. Contributor
testing, builds, and code style are documented under `Developer's note`.

Local observation (2026-10-09): plain `uv lock` accepts both default groups
without changing the dependency resolution. Plain `uv sync` selects the
notebook dependencies, but local installation stopped on access denied while
replacing `.venv` package metadata after downloads succeeded. Environment
installation was incomplete at that point; this was not evidence of a dependency mismatch.

Later observation (2026-10-09), during the focused synchronous-stream check:
the default cache was inaccessible, and retrying with the temporary cache
first hit sandbox network restrictions. An authorized network retry downloaded
the locked dependencies but failed to uninstall existing ipykernel metadata.
Test collection through the existing project interpreter then failed because
the editable `pylabjack` installation was unavailable. The three selected
stream checks initially could not execute; setup repair was separate work.

Current observation (2026-10-09): following the user's environment repair,
plain `uv sync` succeeds without missing-`RECORD` or access-denied warnings
(41 installed packages checked). The three selected fake-LJM synchronous
stream cases passed with `uv run pytest tests/test_stream_sample_times.py -k
'stream_uses_actual_rate_returned_by_estreamstart or
stream_execute_propagates_failure_in_running_loop'`. No full suite or hardware
execution was performed. If interrupted installation leaves an environment
incomplete, prefer recreating the disposable `.venv` and plain `uv sync` over
prolonged individual package repair. Shut down its notebook kernel first and
keep source files and the working notebook intact.

## Configuration integrity

Use plain `uv sync`, `uv lock`, and `uv run` for routine work. The default
groups include the notebook dependencies; no separate selection is needed.
Do not add lock-enforcement or synchronization bypass flags to default commands.

`pyproject.toml` is the source of dependency ranges, groups, Python support,
and build configuration. `.python-version` selects a development interpreter
within `requires-python`. `uv.lock` is generated from those declarations;
never duplicate dependency pins in setup instructions or hand-edit the lock.
After changing dependency declarations, run `uv lock`, review its diff, and
run `uv sync` when the environment needs updating. Include related metadata,
lockfile, and documentation changes together. A plain command is not a reason
to upgrade dependencies or expand the supported Python range.

The uv build backend includes `docs/**` in the source distribution so README links to detailed repository documentation remain available to sdist consumers. Documentation is not installed as wheel package data.

There is still no lint/type-check configuration, CI workflow, native-LJM test, hardware integration suite, tag/release process, or publishing command. Do not invent those success criteria or publish version 0.1.0 without a separate release decision.

## Proportional validation policy

The user prefers low testing overhead (confirmed 2026-10-09). Choose checks
for the actual change; the layers below are available options, not a required
sequence. Orientation, documentation, comments, and simple low-impact edits
may skip test creation and execution. Diff review is usually sufficient for
such edits. Do not add tests solely to mirror the implementation or satisfy a
per-change testing ritual.

For a behavior change, use the smallest focused check that resolves a concrete
uncertainty, preferably by reusing an existing test. Add a focused regression
test when it provides useful evidence, without automatically expanding into
an exhaustive failure matrix or elaborate fake-hardware framework.

Before creating or running comprehensive tests, explain why the focused
approach is insufficient, the proposed scope, and expected overhead, and
obtain explicit user approval. This covers the full pytest suite, broad
regression matrices, and extensive new test infrastructure. An explicit user
request already covering that scope supplies approval. Finish independent
implementation work while awaiting a required answer; do not start the
dependent comprehensive testing until approval arrives.

Stop after sufficient evidence. Do not rerun or broaden checks without a new
change, failure, or unresolved concern. Avoid prolonged test-environment
troubleshooting for incidental permissions or setup failures; report the
limitation and continue useful development, requesting approval before
substantial validation setup. Report checks actually run and briefly note
relevant checks skipped. Hardware authorization remains governed by
`hardware-safety.md`.

1. **Diff hygiene**
   - Run `git status --short` before and after editing.
   - Run `git diff --check` and review the full relevant diff.
   - Preserve unrelated dirty files, especially the notebook.
2. **Lock and environment**
   - When dependency declarations change, regenerate with `uv lock` and review the metadata and lockfile together.
   - Run `uv sync` when the environment needs setup or synchronization, not before every check. Do not use `--active`; keep the project `.venv` isolated.
3. **Device-free tests**
   - When useful, run `uv run pytest <target>` for the relevant test or small selection. Run the full suite only with explicit user approval.
   - Pytest defaults exclude both `native_ljm` and `hardware` markers.
   - The current suite checks public-export boundaries, an isolated installed-package import, static hardware-example placeholders/no-literal-IP policy, immutable/cached software provenance with real temporary Git worktrees and credential-free remote normalization, fake-LJM device construction/close/context and failure contracts, ordered scalar `eNames()` read/write/mixed framing and result metadata, the stream module/capability-ledger contract, interleaved channel splitting, unified grouped/ordered stream-plan normalization and safe rejection boundaries, model-specific sample-time reconstruction, chunk/skip behavior, external scan-start inputs, actual-rate propagation through a fake LJM boundary, and the T7 settling-advisory table/severity/output contract before register writes. It imports the Python wrapper but never opens/searches for a device or invokes a native LJM function.
   - When new behavior tests are warranted, fake or mock the `labjack.ljm` boundary with only the scaffolding needed for the selected behavior.
4. **Package build**
   - Run `uv build` when metadata, layout, or included-file changes warrant packaging verification; a public-code edit alone does not require it.
   - Inspect wheel/sdist contents when inclusion behavior matters. `ljm_startup_configs.json` is presently a repository-only vendor reference and is intentionally absent from distributions.
5. **Native LJM check**
   - Tests that call the separately installed native runtime must use `native_ljm` and must not search for or open a device.
   - No such test exists yet; an ordinary package import is not proof that native LJM loaded successfully.
6. **Opt-in hardware integration**
   - Follow `hardware-safety.md` only after explicit authorization and device confirmation.
   - Record the Python, `labjack-ljm`/LJM, device model/firmware, connection, test configuration, exact command, result, and state restoration.

Ruff and a type checker may be added later, but they are not current success criteria. Do not report them as run unless they are configured, installed, and actually executed.

## Commands that are not generic tests

Do not automatically execute any of the following:

```powershell
uv run python -m pylabjack.labjack_device <DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>
uv run python -m pylabjack._stream <DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>
# any execution of test_labjack_device.ipynb
```

The facade, stream demo, and notebook are hardware-facing. They contain no concrete device identifier: both modules consume the three device-selection values positionally, and the notebook uses all-capital placeholders. The stream module then uses its fixed, untriggered AIN0/AIN1/AIN4, 10 kHz, 1-second, 1000-scans/read, RI-1, auto-settling, ±10 V demonstration. After valid device inputs are supplied these paths can connect, modify registers and process-global LJM settings, start a stream, or generate substantial output.

The strict-JSON parse of `ljm_startup_configs.json` is also not a valid generic check because the vendor-format file intentionally contains `//` comments.

## Notebook policy

- Commit `test_labjack_device.ipynb.template` as the manual hardware test/demo template. Copy it to `test_labjack_device.ipynb` for local use; that working copy is ignored by Git and is not a source of test truth.
- If the working copy already exists, reuse it; never overwrite it while updating or copying the template. Static example checks read the tracked template rather than the local working copy.
- At each development task, compare the working notebook's code and Markdown with the template, even when Git status shows no notebook change. Carry reusable user edits into the template while retaining template-specific copy/setup instructions and all-capital hardware placeholders. Do not copy local device/channel selections, outputs, execution counts, private paths, or identifying metadata. Read the working copy without modifying it; this policy does not install a background watcher.
- Never run it automatically and never replace its selected device from stored output.
- Do not clear outputs, execution counts, or embedded figures without explicit permission; they may be user data.
- Keep the tracked template's code-cell outputs empty and execution counts unset. Before committing template changes, inspect for private paths, IPs, serial numbers, stale exceptions, and measurement data. Local notebook outputs remain user data.
- Notebook code imports dependencies explicitly and must not regress to wildcard imports that leak names such as `np`.
- Keep device, connection, identifier, and physical-channel inputs as visibly all-capital placeholders such as `<DEVICE_IDENTIFIER>`; never commit a usable address or serial number.
- The user explicitly selected `AIN0`, `AIN1`, and `AIN2` for the consecutive multi-register read/plot example. Retain those channel names in that example; other hardware-input placeholders and the prohibition on automatic execution still apply. Its x-axis is reading index, not a controlled sampling schedule.

## Test baseline and next coverage

Keep tests separated into:

- device-free unit/package tests that do not call native LJM functions;
- native-runtime tests marked `native_ljm` that never access a device;
- adapter/contract tests using a controlled fake LJM implementation;
- explicitly authorized hardware integration tests marked `hardware` and excluded by default.

The current tests provide packaging, device-handle lifecycle, data-splitting,
and device-free stream sample-time coverage. The following are candidate
checks when working on the corresponding issue, not a mandatory backlog or
permission to run comprehensive tests:

- the older `configure_register()` numeric/string signatures and absence of its implicit AIN writes;
- specialized numeric-array/string/byte/address command-response variants;
- exact requested scan/sample counts and final-block truncation;
- authorized model/firmware hardware checks of the manual-derived actual-rate and within-scan timing profiles;
- skipped-sample conversion to `NaN`;
- stream stop and worker cleanup on every exception path;
- trigger timeout unit conversion and cancellation;
- synchronous versus asynchronous completion and exception propagation;
- the single documented import path and package exports.
