# Codex Engineering Instructions

Read `docs/PRD.md` in full before modifying code. This PRD is authoritative for v1 scope and acceptance criteria. Do not stop at a design or skeleton; implement the complete app, tests, packaging and docs.

## Non-negotiable truthfulness
- iCUE itself performs automatic game-linked **software mapping** through Linked App.
- Our application detects/organizes/guides/verifies *user attestation*, not direct hardware profile commands.
- Never fabricate a profile-switch SDK, direct iCUE API, programmatic onboard mapping switch or 'active iCUE profile' readback.
- Label process detection, expected mapping, user-configured link and hardware-tested confirmation separately.
- Do not silently mutate iCUE private files, send HID commands or bypass anti-cheat.
- Never claim hardware tests passed unless run with controller and iCUE present; record `REQUIRES WINDOWS HARDWARE VALIDATION` otherwise.

## Engineering standards
- Python 3.11+ with PySide6, pytest, ruff, mypy and PyInstaller; app must install/run on Windows 10/11.
- Dependency inversion at OS boundaries; every Win32/process/registry behavior mockable.
- No admin privilege, telemetry, arbitrary shells, unsafe file writes, game input injection, secret collection or cloud dependencies.
- SQLite persistence in `%LOCALAPPDATA%`; validated, versioned JSON export/import; backups; robust error handling.
- Build Windows CI artifact; no release publishing, force pushes or repo settings changes without explicit permission.
- Meaningful automated unit/integration tests; finish only after running available checks and documenting real outcomes.

## Workflow
1. Inspect existing repository and official constraints.
2. Implement P0 and P1 requirements in `docs/PRD.md` in sequence.
3. After each milestone, run tests and fix failures before moving on.
4. Build/smoke-test on Windows whenever Windows runner or workstation available.
5. Document exact startup, test, package steps and genuine limitations in `README.md` and `IMPLEMENTATION_REPORT.md`.
6. If unavailable hardware/OS blocks verification, do everything independently verifiable and precisely document remaining user acceptance steps instead of leaving the product as a stub.
