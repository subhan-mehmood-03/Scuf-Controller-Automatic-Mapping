# Product Requirements Document — SCUF Automatic Mapping

**Version:** 1.0 | **Status:** Implementation-ready | **Target:** Windows 10/11, SCUF Envision Pro Wireless, Corsair iCUE 5+ | **Repository:** `subhan-mehmood-03/Scuf-Controller-Automatic-Mapping`

## 0. Executive directive to Codex
Build, test, document and package a production-quality, local-first Windows desktop application that detects the active PC game, maintains game-to-iCUE-software-profile associations, and makes the native iCUE Linked App configuration clear and verifiable. iCUE remains running and controls actual SCUF Envision Pro mappings. The app **MUST NOT** claim it can change iCUE profiles using an unverified API. Do not stop at scaffolding or a proof of concept: implement the complete v1 scope, automated tests, Windows build workflow, startup instructions, error handling, and manuals. If a system feature is unverifiable without Windows/iCUE/hardware, label it `REQUIRES WINDOWS HARDWARE VALIDATION` and include repeatable manual instructions rather than fabricating success. Never falsely claim 100% hardware verified.

## 1. Product goals and non-goals
### Goals
- Attractive, reliable desktop GUI showing foreground application, matched game, intended iCUE profile, setup status, diagnostic status and recent events.
- Add/edit/delete/disable unlimited game mappings, each tied to executable file identity and iCUE profile name; import/export JSON with schema version and validation.
- Scan foreground windows and optionally enumerate running processes to help users discover executable names/paths without injecting into games.
- iCUE setup assistant walks the user through creating a software profile, setting mappings, and assigning its Linked App; keeps user-verifiable status and tracks confirmation date; never implies an automatic config write occurred unless a supported integration exists and is proven.
- Minimize to system tray, launch at Windows login (opt-in), pause/resume monitoring, configurable check interval, default profile / unmatched behavior, clear notifications, searchable event log.
- Run locally/offline; no accounts, telemetry, driver replacement, packet capture, game memory inspection, or admin privileges by default.
- Verifiable distribution: Python dev launch, PyInstaller packaged Windows EXE, CI unit tests, written hardware acceptance checklist.

### Non-goals for v1
- Changing onboard controller profile slots over USB/wireless; SCUF hardware mapping and iCUE software profiles are different mechanisms.
- Writing iCUE profile files, editing iCUE internal databases, invoking private/undocumented iCUE APIs, reverse engineering dongle/controller HID commands.
- Sending controller inputs, simulating macros, injection/hooks into protected games, bypassing anti-cheat, attempting Windows process privilege elevation, or reading game memory.
- Guaranteeing the current iCUE active profile can be queried externally (unless an official supported API is identified and tested).
- Silently installing iCUE, firmware updates or modifying the controller.

## 2. Grounded capabilities and constraints
- SCUF Envision Pro Wireless connects through its supplied SLIPSTREAM USB receiver, not generic Bluetooth. A wired USB-C connection is used for onboard profile setup.
- While iCUE runs, iCUE software mappings take precedence over out-of-box/onboard mappings. iCUE can associate software profiles with application executables via `Linked App`.
- Software profile switching is performed **by iCUE's own association mechanism**, not by this application's detection loop. Our detection and association database support discovery, onboarding, reconciliation and monitoring.
- The app's 'desired', 'configured (user attested)' and 'verified on hardware (user attested)' statuses MUST be distinct from 'active in iCUE', which is **unknown** if no supported read API exists. Use text such as `Expected iCUE profile` rather than `Activated profile`.
- Cannot assume profile import/export synchronization works via files that iCUE owns. User manually creates/links profile in iCUE. Provide copy buttons and open iCUE option only when executable location confirmed, without launching arbitrary files.
- iCUE may have existing Linked App conflicts. Detect duplicate mapping in our database and warn, but do not claim to detect iCUE conflicts externally.

**Official references (verify at build time):**
- https://help.corsair.com/hc/en-us/articles/360058672092-iCUE-How-to-Set-up-and-manage-profiles-in-iCUE-4-or-newer
- https://www.scufgaming.com/us/en/gaming/products/pc/envision/
- https://customercare.scufgaming.com/hc/en-us/articles/23528201411853-How-to-Software-Remap-in-iCUE-for-SCUF-Envision
- https://customercare.scufgaming.com/hc/en-us/articles/23530811859085-How-to-Hardware-Remap-Save-Profiles-in-iCUE-on-Envision

## 3. Intended user journey
1. Run installer/EXE. First-run wizard checks Windows compatibility; explains SLIPSTREAM dongle and iCUE prerequisite; offers link to official iCUE download (does not install anything silently).
2. App shows `iCUE running` status based on a configurable safe allowlist of process names, with caution that process existence is not proof controller is connected or mappings active.
3. Click `Add game`, choose a trusted local `.exe` with native file picker or `Use foreground application`; name game and profile (`Fortnite Competitive`). Avoid automatically assuming launcher EXE is the actual game.
4. Setup guide displays manual steps: in iCUE create software profile; remap paddles/SAX as needed; assign `Linked App` to the game's exact executable; leave iCUE running. User explicitly checks `I linked this game in iCUE` and optional `I validated paddle behavior in game`. Store timestamps and notes.
5. When the game is foreground, application updates the UI and tray, emits one deduplicated event, and shows expected profile and verification state. Actual activation is by iCUE.
6. On unmatched foreground program, show `No game mapping`; do not switch anything or spam notifications. Minimize common Windows system UI apps from notifications.
7. Settings: enable autostart (opt-in), pause, quiet notifications, diagnostics and event retention, backup/export/import.

## 4. Functional requirements (prioritized)
### P0: Must ship
**FR-001 Foreground detection.** Poll current foreground HWND with Win32 API (`GetForegroundWindow`, `GetWindowThreadProcessId`, `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`, `QueryFullProcessImageNameW`). Encapsulate Windows calls behind `ForegroundProvider`. Handle missing HWND, UAC/protected processes, exceptions, rapid focus changes, process exit and empty paths gracefully. Canonicalize only for comparison; retain display path. Never inspect process memory or bypass permissions. Configurable interval default 1000 ms; debounce candidate after two consecutive observations / ~1–2 seconds. Do not block UI thread.

**FR-002 Rule matching.** Deterministic ordered resolution: enabled exact normalized full executable path first; enabled executable basename fallback only when unambiguous; else unmatched. No substring match; warn on duplicate basename/path, conflicting records and missing executable. Case-insensitive Windows semantics. If multiple rules tie, surface conflict and do not guess. Profile names case-preserving strings; trim and reject empty. Stable UUID IDs.

**FR-003 Profile library CRUD.** Add, edit, delete (with confirmation), enable/disable, search/sort profiles. Fields: `id`, `game_name`, `executable_path` (optional if discovery not complete), `executable_name`, `icue_profile_name`, `enabled`, `linked_app_attested_at`, `mapping_test_attested_at`, `notes`, `created_at`, `updated_at`. Display user confirmations prominently. No buttons that purport to change hardware slots.

**FR-004 Status/dashboard.** Display: foreground process, matched game, expected iCUE profile, mapping state (`not configured`/`user confirmed linked`/`user confirmed tested`), iCUE process presence (`detected`/`not detected`/`unknown`), monitoring state (`active`/`paused`), and last detection time. Never show an unverifiable `confirmed active iCUE profile` label.

**FR-005 Guided setup.** Step-by-step wizard with `Copy executable path`, `Copy profile name`, `Open executable folder` (only existing trusted path), `Open iCUE` (optional, only detected executable), official help link, and user attestation controls. Include wirelessly-connected controller setup hint. Explain iCUE Linked App association and software versus onboard memory. Do not capture physical mappings as applied when not actually applied.

**FR-006 Persistence.** SQLite using standard `sqlite3` in `%LOCALAPPDATA%/SCUFAutomaticMapping/`; schema migration via integer user_version; ACID transactions; parameterized SQL; sensible backup and recovery; no migration that drops user data silently. JSON import/export with `schema_version`, strict limits, type validation, duplicate resolution preview, atomic export/write and error messages. Do not store config inside Program Files or the PyInstaller extraction directory.

**FR-007 Diagnostics and logs.** Rotating local logs, max 5 files × 2 MB, no network logging; redact username/home directories from exported diagnostics by default; user opt-in for raw full process paths. Retain application events max 30 days or 5000 entries (configurable within caps). Capture win32 failures without crashing.

**FR-008 Windows GUI and tray.** PySide6 GUI with pages Dashboard, Games/Profiles, Setup, Activity, Settings, About. Consistent dark theme with accessible contrast, proper keyboard navigation and screen reader labels where practical. Use QSystemTrayIcon for minimize, restore, pause and exit. Gracefully handle tray unsupported. On Close, minimize only if explicitly configured; otherwise quit normally. No console in release EXE.

**FR-009 Autostart.** Off by default. When enabled, add only this application's executable to current-user Windows `Run` registry key (`HKCU`), with validated paths and reversible removal; do not require admin access. In dev mode, support a safe, explicitly chosen launch command or disable autostart with explanation. On uninstall, document removal.

**FR-010 Packaging.** `pyproject.toml`, dependency lock or constrained versions, `requirements-dev.txt` or optional `dev` group, `README.md`, Windows build scripts, PyInstaller `.spec`, GitHub Actions test/build jobs and uploaded EXE as CI artifact. Publishable tagged release workflow optional, but don't publish without approval. App name `SCUF Automatic Mapping`, internal version `0.1.0`. Include LICENSE choice (MIT suggested; repository owner must approve) and `.gitignore`.

### P1: Strongly preferred for complete v1
**FR-011 Running-game discovery.** Display a list of current processes with basename/path (best-effort) and foreground selection. Filters, process exclusions, and no unsanctioned process interrogation.
**FR-012 Notifications.** Opt-in tray popups on game match changes only; debounce/rate limit and avoid repeated notifications when switching apps briefly or when game loses focus.
**FR-013 Mockable adapter.** Define `ICueStatusProvider` (`get_process_status`) and `ProfileActivationEvidence` that never claims actual activation. Future official integrations may implement a separate interface only after provenance/documentation verified and permission granted.
**FR-014 Startup/recovery.** Clean crash reporting, last-known configuration, corrupt DB backup + explicit recovery prompt; never silently overwrite corrupted data.

## 5. Data model and APIs
Use a clean separation:
- `domain/models.py`: dataclasses/pydantic-equivalent lightweight validation and enums.
- `domain/matcher.py`: pure functions for matching, conflicts and transitions.
- `infrastructure/foreground_win32.py`: isolated platform-specific foreground API.
- `infrastructure/processes.py`: best-effort iCUE process status.
- `infrastructure/repository_sqlite.py`: schema and transactions.
- `infrastructure/import_export.py`: validated JSON.
- `application/monitor_service.py`: worker thread or QTimer, debounce and state transitions; never mutates UI from worker threads.
- `ui/`: PySide6 presentation with signal/slot pattern.
- `main.py`: lifecycle, lock or single-instance policy, exception handling and logging.

Example exported JSON (illustrative, no secrets):
```json
{
  "schema_version": 1,
  "profiles": [
    {
      "id": "REPLACE-WITH-UUID",
      "game_name": "Fortnite",
      "executable_path": "C:\\Games\\Fortnite\\FortniteClient-Win64-Shipping.exe",
      "executable_name": "FortniteClient-Win64-Shipping.exe",
      "icue_profile_name": "Fortnite Competitive",
      "enabled": true,
      "linked_app_attested_at": null,
      "mapping_test_attested_at": null,
      "notes": ""
    }
  ]
}
```
Profile-import versioning must define defaults for optional date fields; do not assume this illustrative JSON includes every database column.

## 6. UX details
- Header: foreground game, status tag `Expected mapping: X`, source label `iCUE native Linked App`.
- Left nav: Dashboard / Games / Setup / Activity / Settings / About.
- Main table: Game | EXE | Expected Profile | iCUE Link | Hardware Test | Enabled | Edit.
- Badges must not imply direct controller command was sent.
- Onboarding explains wireless USB dongle; never label it Bluetooth.
- Explain why user must manually configure profile in iCUE; offer actionable links and small troubleshooting messages.
- No mandatory account, login or internet access; only optional web help links.

## 7. Safety, security, privacy and performance
- All process inspection read-only; avoid opening protected processes beyond query-only access. No keylogging, HID packet injection, kernel drivers, DLL injection, anti-cheat modification, global keyboard hooks or game input automation.
- No arbitrary shell execution or `shell=True`; no unverified external code, downloads or silent installers. Validate path existence, user choice and file extension when opening exe/folders.
- Input normalization, max string lengths, Unicode handling, directory traversal safe exports, JSON payload size cap (e.g. 5 MB), strong schema validation, parameterized DB access.
- No personal or gameplay data is transmitted anywhere. Never require admin. Respect app lifecycle and clean background worker shutdown.
- Monitor normally at ~1 Hz and idle low CPU; avoid aggressive process polling and full enumeration every second. Target less than 1% CPU at idle on typical Windows desktop, approximate and hardware-dependent.
- Make all external dependencies explicit; pin or constrain compatible versions; add vulnerability/dependency review if available.
- Follow Windows policies; don't spoof controller devices, interfere with online anti-cheat, or claim controller actions occurred without evidence.

## 8. Detailed testing strategy
### Unit tests (pytest, run on Windows and Linux where possible)
- `test_matcher.py`: exact path priority, case-insensitivity, fallback unambiguous basename, duplicate ambiguity, disabled rules, Unicode path, null foreground, same-game transition, no repeated events.
- `test_monitor.py`: fake foreground provider sequence, two-sample debounce, rapid game/desktop changes, pause/resume, cancellation, timeout/errors, late worker events and event deduplication.
- `test_repository.py`: CRUD, transaction rollback, unique IDs, migration from empty and previous schema, invalid input, database reopen persistence, corrupt file handling without data loss.
- `test_import_export.py`: round trip, version handling, malformed JSON, missing mandatory fields, type failures, max size, duplicate handling, Unicode, safe atomic write.
- `test_icue_status.py`: mocked process list for running/not running/unknown; clear that running is not controller activation proof.
- `test_settings.py`: defaults, range limits, opt-in autostart and reversible fake registry adapter (no actual registry writes in tests).
- `test_privacy.py`: exported diagnostics redact user directory.

### GUI integration tests (headless Qt when feasible)
- `pytest-qt` or equivalent: app launch, navigation, add/edit/delete, profile setup checklist, search, monitor status changes, pause/resume, failed paths, simulated corruption and clean shutdown. `QT_QPA_PLATFORM=offscreen` in CI for mockable UI tests.

### Windows integration tests
- Validate foreground process query against a fixture window; ensure protected/inaccessible processes return `unknown` with no crash.
- Verify optional autostart under test-owned mock registry layer; manually validate HKCU setting on real Windows.
- Package EXE with PyInstaller on `windows-latest`; launch `--self-test` or `--diagnostics` non-GUI smoke mode to verify packaging imports/config and exits code 0. Must not require iCUE installed in CI.
- CI jobs: Linux unit tests; Windows full unit + GUI tests, static lint/type checks, PyInstaller build and artifact, smoke test. If a test suite relies on display/hardware, keep separate rather than hiding failures.

### Manual hardware acceptance (MANDATORY, user Windows PC)
- [ ] iCUE is installed and displays Envision Pro connected through its SLIPSTREAM USB dongle.
- [ ] Two genuinely different iCUE software profiles have visibly different paddle mappings.
- [ ] Each iCUE profile has its intended game `.exe` under Linked App.
- [ ] Launch Game A in foreground: app recognizes A; iCUE profile visibly changes or mapping behavior tested in-game.
- [ ] Switch to Game B: app recognizes B, and different paddle mapping functions as configured.
- [ ] Alt+Tab to desktop and back: no false game switch or repeated notifications; mapping behavior follows iCUE.
- [ ] Restart iCUE: app reports presence change without pretending it controls the controller.
- [ ] Disconnect/reconnect wireless dongle: app does not crash or report invented controller readiness.
- [ ] Reboot Windows with app autostart enabled: app starts, restored mapping list, iCUE Linked App operates as configured.
- [ ] Test packaged EXE without Python installed; persists config under LocalAppData.
- [ ] Confirm no elevated privileges, network access, anti-cheat errors, or unwanted interference.

**Hardware results must be recorded with pass/fail/date/actual observation; automation cannot substitute.**

## 9. Acceptance criteria / Definition of Done
1. Dev install (`py -m venv .venv`, dependency install, `python -m scuf_auto_mapping`) starts GUI on supported Windows.
2. `pytest` green; linter and type check green; coverage >=85% for domain/application/infrastructure (exclude GUI generated and platform wrappers with explicit justification). No skipped critical tests without reason.
3. Windows CI builds standalone EXE and passes packaged smoke test; downloadable CI artifact.
4. User can create a profile with game executable, guide through native iCUE Linked App, mark configured/tested, and recover it after restart.
5. Foreground detection reliably changes the *expected* profile display; always handles unmatched app without change and without notification spam.
6. iCUE detection accurately reports process presence only; UI never misreports hardware activation.
7. No network/telemetry; no admin need; safe handling of malicious JSON/path inputs and inaccessible processes.
8. README includes download, setup, screenshots when real app is built, exact run/build/test commands, iCUE configuration and realistic troubleshooting.
9. Hardware checklist included and left `NOT YET VERIFIED` until tested on a real SCUF Envision Pro + iCUE computer. **Do not call product fully hardware-verified merely because CI passes.**
10. An `IMPLEMENTATION_REPORT.md` enumerates files, design, executed commands with actual outputs, current limitations, CI status if available, and Windows/hardware verification outstanding.

## 10. Implementation plan (Codex execute sequentially; no stop after each stage)
**Milestone 1: Project skeleton and pure core.** Scaffold package/pyproject; implement validated model, deterministic matcher, repositories, profile JSON migration; unit tests.
**Milestone 2: Windows detection.** Win32 foreground wrapper with injection-friendly fake; monitor state machine/debounce; iCUE presence provider; test all errors.
**Milestone 3: GUI.** Dashboard/library/setup wizard/activity/settings/system tray; no blocking UI; implement all flows with tests.
**Milestone 4: OS integration and safety.** HKCU opt-in autostart, diagnostics, error handling, JSON backup/restore, secure input validation.
**Milestone 5: Packaging and release readiness.** PyInstaller spec, Windows CI, build script, README + screenshots only if actually generated, smoke test, implementation report.
**Milestone 6: Verify and remediate.** Run tests/lint/type/coverage, fix discovered failures, execute Windows packaged smoke test where accessible, review all acceptance criteria; explicitly identify manual Windows/iCUE/SCUF validation steps not executed in environment.

## 11. Required documented commands and expected shape
Project may adjust dependency manager with justification. Aim for:
```powershell
# Development (PowerShell, from repository root)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m scuf_auto_mapping

# Automated checks
python -m pytest -q
python -m ruff check .
python -m mypy src

# Portable EXE
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```
Release `dist/SCUF-Automatic-Mapping.exe` or clearly documented equivalent. Make the exact commands work by completion; no documentation-only features.

## 12. Repository and collaboration
- Use supplied repo URL; do not commit secrets, build outputs, `.venv`, LocalAppData, personal process logs, or generated large binaries to Git.
- Do not force push, delete branches/history, change repository visibility, or publish a release without owner authorization.
- Before altering an existing source file, inspect it; preserve user changes. Commit in reviewable logical steps. Add standard `.github/workflows/ci.yml`.
- If repo is inaccessible, deliver a local build with all repository files and precise upload steps. Do not claim push succeeded.
- No autonomous credential collection, secrets injection or privileged CI actions.

## 13. Optional v2 ideas (out of scope unless P0/P1 completed)
- Game catalog/Steam library import by user opt-in; robust per-game executable matching remains prerequisite.
- Official supported API integration if Corsair publishes a true profile control/read endpoint in future; requires proof and tests.
- Customizable controller diagram showing *planned* button mappings, explicitly not synchronized with iCUE unless supported.
- Signed installer/updater only after separate security review and owner approval.
