# Windows + iCUE + SCUF Envision Pro Hardware Acceptance

**Status: NOT YET VERIFIED — requires execution on user's physical Windows PC.**

Tester: ______  Date: ______  Windows version: ______  iCUE version: ______  App version: ______

| Test | Expected result | Actual observation | Pass/Fail |
|---|---|---|---|
| Launch EXE without developer Python | GUI launches and retains profile data | | |
| Envision Pro connected over included SLIPSTREAM USB receiver | iCUE recognizes controller | | |
| Configure game A profile + Linked App in iCUE | iCUE auto-applies game A mapping | | |
| Configure game B with different paddle map | Game B's behavior distinct | | |
| Game A in foreground | App identifies A and expected profile | | |
| Switch focus to B | App identifies B and expected profile | | |
| Alt+Tab out/back | No spam or false success status | | |
| Quit/relaunch iCUE | Presence displayed correctly | | |
| Unplug/reconnect receiver | App remains responsive | | |
| Reboot after opt-in autostart | App launches and restores configuration | | |
| Export/import profile JSON | All valid records restored | | |
| Game has no profile | No mapping guessed, no repeated alert | | |
| No admin prompts, cloud/telemetry or anti-cheat issues | Safe runtime | | |

**Rule:** Only mark 'hardware verified' when paddle behavior is actually checked in games, not just when the Python detector shows an expected profile.
