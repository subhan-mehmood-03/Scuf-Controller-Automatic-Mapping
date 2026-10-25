# Implementation report — 0.1.0

Implementation date: **2026-10-24 (America/Chicago)**.

## Scope and evidence boundaries

Implemented the v1 local desktop application described by `docs/PRD.md` and
preserved the supplied `docs/HARDWARE_ACCEPTANCE.md`. The working repository and
remote initially had no commits. Starter material consisted of requirements and
instructions, not application source.

The application organizes and detects **expected iCUE software profiles**.
iCUE's native Linked App mechanism performs actual switching. Active profile
readback and controller readiness remain unknown. No undocumented iCUE API,
controller command, private configuration write, game hook, or input automation
was introduced.

**REQUIRES WINDOWS HARDWARE VALIDATION.** No physical controller/game results
are claimed. The hardware acceptance checklist remains NOT YET VERIFIED.

## Delivered files and design

| Files | Responsibility |
|---|---|
| `pyproject.toml`, `.gitignore` | Installable src-layout package, constrained runtime/dev dependencies, test/lint/type/coverage configuration, ignored personal/build data |
| `src/scuf_auto_mapping/domain/models.py` | UUID profiles, Windows executable identity validation, timestamps, attestation consistency, bounded validated settings, explicit activation evidence model |
| `domain/matcher.py` | Enabled exact normalized path priority, unambiguous basename fallback, conflict warnings; pure functions |
| `application/monitor_service.py` | Mockable foreground interface, two-observation debounce, pause/resume, transition deduplication, access/error tolerance |
| `infrastructure/foreground_win32.py` | Query-only Win32 foreground APIs, correctly typed handles, limited-information process access, guaranteed handle close |
| `infrastructure/processes.py` | Best-effort read-only process discovery, injectable iCUE presence interface; no activation claims |
| `infrastructure/repository_sqlite.py` | SQLite schema/user_version migration, validated transactional CRUD, settings, bounded searchable events, consistent backup |
| `infrastructure/import_export.py` | Versioned strict JSON validation, defaults for omitted optional dates, bounded payload, duplicate-ID rejection, conflict preview, fsync/atomic replace |
| `infrastructure/system.py` | LocalAppData paths, 5 × 2 MB rotating logs, diagnostic redaction, injectable reversible HKCU Run integration |
| `ui/window.py` | Six dark-theme pages, profile editor, setup confirmations, process discovery, filters/sort, notifications, tray, settings, exports/backups; interruptible QThread and queued signals |
| `main.py`, `__main__.py` | Lifecycle, local instance lock, crash reporting, explicit corrupt-data recovery, isolated CLI and GUI smoke modes |
| `tests/test_core.py` | Validation, matching, debounce, repository, imports, privacy, settings/presence tests |
| `tests/test_adapters.py` | Mocked Win32 and registry failures, inaccessible processes, separate live Windows read-only query |
| `tests/test_gui.py`, `tests/test_lifecycle.py` | Navigation, library CRUD, search, setup attestations, reset stale confirmations, settings, export, failed paths, notifications, stale snapshots, worker shutdown, recovery persistence |
| `scripts/entrypoint.py`, `SCUF-Automatic-Mapping.spec`, `scripts/build_windows.ps1` | Windowed portable EXE, isolated packaged persistence and GUI smoke checks |
| `.github/workflows/ci.yml` | Ubuntu/Windows test matrix, lint/types/coverage, Windows package build and artifact upload; read-only repository permissions |
| `scripts/capture_screenshot.py`, `docs/images/` | Actual rendered UI screenshots with synthetic data; reproducible without personal process logs |
| `README.md`, `LICENSE`, `AGENTS.md`, `docs/` | Usage, architecture, troubleshooting, reserved-rights license per owner choice, original requirements and mandatory manual acceptance |

The GUI owns SQLite and receives immutable observation snapshots from its worker.
Full process enumeration runs every ten seconds for presence, or on explicit
discovery; foreground polling defaults to one second. Worker cancellation checks
every 50 ms between polls. Configuration edits replace worker snapshot references.
Late pre-pause or post-shutdown observations are ignored.

Changing executable identity or expected profile clears prior attestations.
Default/unmatched settings are reminders only. Imports preview ID replacement
versus skipping and retain executable conflicts for explicit user resolution.
Corrupt database recovery preserves original bytes and requires confirmation
before a fresh database is created at the normal persistent path.

## Commands actually executed

Commands below used the repository virtual environment's Python on Windows 11
x64, Python **3.13.4**, Qt/PySide6 **6.10.3**, PyInstaller **6.22.3**.

| Command | Actual result |
|---|---|
| `git ls-remote origin` | Success; empty remote, no existing refs |
| `python -m venv .venv` | Success |
| `.venv\Scripts\python -m pip install -e ".[dev]"` | Initial sandbox network failure; retried with approved network access and installed successfully |
| `python -m pytest -q --cov --cov-report=term-missing` with `QT_QPA_PLATFORM=offscreen` | **45 passed in 0.78s**, coverage **99.10%** (334 statements, 3 missed); required threshold 85% passed |
| `python -m ruff check .` | **All checks passed!** |
| `python -m mypy src` | **Success: no issues found in 16 source files** |
| `python -m scuf_auto_mapping --self-test` | **SCUF Automatic Mapping 0.1.0 self-test passed; Qt 6.10.3; hardware unverified** |
| `python -m scuf_auto_mapping --gui-smoke` with offscreen Qt | Exit code **0**; temporary database and actual UI opened/closed |
| `python scripts/capture_screenshot.py` with offscreen Qt | Two actual UI screenshots generated; inspected dashboard rendering and corrected offscreen font loading |
| `python -m PyInstaller --noconfirm --clean SCUF-Automatic-Mapping.spec` | Windows windowed EXE built successfully; final packaged smoke results recorded below |
| `powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1` with virtualenv on PATH | Exit code **0**. Final output: **Built dist/SCUF-Automatic-Mapping.exe; packaged self-test passed.** Both packaged `--self-test` and offscreen `--gui-smoke` exited **0**. |
| `git push -u origin main` | Success: **[new branch] main -> main**, tracking `origin/main` |

Coverage intentionally excludes only the ctypes Win32 wrapper from the numeric
threshold. Mocked API calls and the live Windows query still test it; neither can
prove behavior in every protected game or desktop. GUI code is tested separately
and does not inflate the core coverage denominator. Linux CI skips the live
Win32 query with an explicit platform reason. No physical tests are silently
skipped or described as automated successes.

Remediation during testing included a retained database connection in a test,
typed GUI widget unions, stale confirmation reset, late snapshot suppression,
explicit instance-lock release when recovery is declined, and clean worker
shutdown on application quit. All automated suites were rerun after changes.

## Packaging and repository delivery

Final portable EXE: `dist/SCUF-Automatic-Mapping.exe`, **47,910,803 bytes**.
Both packaged persistence/import and GUI smoke tests passed on this Windows
workstation. The EXE is excluded from Git; CI is configured to upload it as an
artifact. This is not a clean-machine-without-Python acceptance result.

The implementation was committed in logical steps (`7b1809f` core and adapters;
`11035b0` GUI and packaging) and pushed successfully to
`https://github.com/subhan-mehmood-03/Scuf-Controller-Automatic-Mapping.git`.
The push initially failed automatic approval review; read-only verification that
the PRD's explicitly named repository matched origin resolved the rejection.

**Remote CI status: NOT CONFIRMED.** The GitHub connector returned 404 for
repository access, while the configured Git remote authenticated successfully.
Do not interpret the local Windows test/build results as a passed remote Linux
or Windows workflow. Check the repository's Actions tab for run results and
the Windows artifact. README, screenshots, and this report accompany the final
documentation commit.
No release was published, no force push performed, and no repository visibility
or permissions changed.

## Official capability verification

All four PRD official links were fetched and read at implementation time.
Corsair's profile guide describes application associations under Linked App.
SCUF's software guide describes mappings while iCUE is running. The Envision
manual and hardware guide distinguish software mappings, SLIPSTREAM connectivity,
and USB-C requirements for onboard saves. Source links appear in README.
No official external profile activation/read API was assumed or implemented.

## Remaining manual validation and limitations

- Physical Envision Pro, iCUE 5+, receiver reconnect, distinct paddle mappings in
  two games, focus changes, and actual switching: **NOT YET VERIFIED**.
- Reboot autostart and real HKCU integration: **REQUIRES WINDOWS HARDWARE VALIDATION**.
  Automated registry tests use only an injected fake and never modify Run values.
- EXE on a clean Windows machine without Python, Windows 10 behavior, high-DPI
  accessibility/screen-reader review, protected games and anti-cheat compatibility:
  require the manual checklist; local workstation packaging is not a substitute.
- Idle CPU <1% is a target, not a measured acceptance pass. Polling is bounded and
  best-effort process queries may still incur hardware-dependent latency.
- There is no prior released schema to migrate; schema 0 (empty) migrates to 1.
  Future database versions are refused, not downgraded or silently discarded.
- JSON import/export caps are per-file; profile count in SQLite has no artificial
  cap. Large libraries should be split for portable interchange.
- Diagnostic redaction protects home/user-directory names by default, not all
  potentially sensitive custom notes/names. Review exports before sharing.
- Portable builds are unsigned and no installer/updater is included. Owner chose
  all rights reserved; no MIT license or public release is implied.

Record real pass/fail/date/observations in `docs/HARDWARE_ACCEPTANCE.md` before
calling this product hardware-verified.
