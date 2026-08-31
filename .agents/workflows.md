# Development and validation workflows

Last workflow review: 2026-08-30

## Official uv baseline

The repository is a uv-managed library with an `uv_build` backend, `src/pylabjack` package, committed `uv.lock`, and Python 3.11 development pin. Use uv rather than global `pip` or an activated external environment.

```powershell
# Exact default development environment (runtime + dev group).
uv sync --locked

# Device-free default suite. The lock has already been synchronized.
uv run --locked --no-sync pytest

# Validate that dependency metadata still matches the committed lock.
uv lock --check

# Build the source distribution and wheel.
uv build

# Add the optional notebook dependencies when deliberately working on it.
uv sync --locked --group notebook
```

`uv.lock` is committed and must change with dependency metadata. The default `dev` group contains pytest; the non-default `notebook` group contains ipykernel and Matplotlib. The project supports Python `>=3.11,<3.12`; `.python-version` selects 3.11 and uv may install a managed interpreter.

The uv build backend includes `docs/**` in the source distribution so README links to detailed repository documentation remain available to sdist consumers. Documentation is not installed as wheel package data.

There is still no lint/type-check configuration, CI workflow, native-LJM test, hardware integration suite, tag/release process, or publishing command. Do not invent those success criteria or publish version 0.1.0 without a separate release decision.

## Safe validation ladder

Use the lowest layer that provides meaningful evidence for the change, and report skipped layers.

1. **Diff hygiene**
   - Run `git status --short` before and after editing.
   - Run `git diff --check` and review the full relevant diff.
   - Preserve unrelated dirty files, especially the notebook.
2. **Lock and environment**
   - For metadata edits, run `uv lock --check`; regenerate intentionally with `uv lock` when requirements changed.
   - Run `uv sync --locked` before validation. Do not use `--active`; keep the project `.venv` isolated.
3. **Device-free tests**
   - Run `uv run --locked --no-sync pytest`.
   - Pytest defaults exclude both `native_ljm` and `hardware` markers.
   - The current suite checks public-export boundaries, an isolated installed-package import, static hardware-example placeholders/no-literal-IP policy, immutable/cached software provenance with real temporary Git worktrees and credential-free remote normalization, fake-LJM device construction/close/context and failure contracts, ordered scalar `eNames()` read/write/mixed framing and result metadata, the stream module/capability-ledger contract, interleaved channel splitting, unified grouped/ordered stream-plan normalization and safe rejection boundaries, model-specific sample-time reconstruction, chunk/skip behavior, external scan-start inputs, actual-rate propagation through a fake LJM boundary, and the T7 settling-advisory table/severity/output contract before register writes. It imports the Python wrapper but never opens/searches for a device or invokes a native LJM function.
   - New behavior tests should fake or mock `labjack.ljm` calls.
4. **Package build**
   - Run `uv build` after changing metadata, layout, included files, or the public package.
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

- Treat `test_labjack_device.ipynb` as a user-owned manual hardware test, not a source of test truth.
- Never run it automatically and never replace its selected device from stored output.
- Do not clear outputs, execution counts, or embedded figures without explicit permission; they may be user data.
- Before intentionally committing notebook changes, inspect outputs for private paths, IPs, serial numbers, stale exceptions, and large measurement data.
- Notebook code imports dependencies explicitly and must not regress to wildcard imports that leak names such as `np`.
- Keep device, connection, identifier, and physical-channel inputs as visibly all-capital placeholders such as `<DEVICE_IDENTIFIER>`; never commit a usable address or serial number.

## Test baseline and next coverage

Keep tests separated into:

- device-free unit/package tests that do not call native LJM functions;
- native-runtime tests marked `native_ljm` that never access a device;
- adapter/contract tests using a controlled fake LJM implementation;
- explicitly authorized hardware integration tests marked `hardware` and excluded by default.

The current tests provide packaging, device-handle lifecycle, data-splitting,
and device-free stream sample-time coverage. Add focused tests before fixing
each remaining source-level issue, including:

- the older `configure_register()` numeric/string signatures and absence of its implicit AIN writes;
- specialized numeric-array/string/byte/address command-response variants;
- exact requested scan/sample counts and final-block truncation;
- authorized model/firmware hardware checks of the manual-derived actual-rate and within-scan timing profiles;
- skipped-sample conversion to `NaN`;
- stream stop and worker cleanup on every exception path;
- trigger timeout unit conversion and cancellation;
- synchronous versus asynchronous completion and exception propagation;
- the single documented import path and package exports.
