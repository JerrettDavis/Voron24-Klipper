# Handoff — voron24 bring-up (written 2026-10-12, ~22:05 CDT)

Read `README.md` first (full hardware, layout, ordered calibration plan). This file is *state + gotchas*.

## Access / basics
- Printer Pi: `ssh jd@voron24.jerrettdavis.com` (host key already accepted). Config repo = `~/printer_data/config` (this repo, `origin` = `JerrettDavis/voron24-klipper`, branch `main`). Workflow: edit locally → `git push` → on Pi `git pull --ff-only` → restart as needed.
- Moonraker API on the Pi at `localhost:7125` (run via `ssh … 'curl …'`). Gcode: `curl -X POST localhost:7125/printer/gcode/script --data-urlencode "script=…"`; console output: `/server/gcode_store?count=N`. Restart Klipper: `POST /printer/restart` (`/printer/firmware_restart` after errors). Camera snapshot: `curl localhost/webcam/?action=snapshot` (overhead view; **cannot judge Z**; toolhead shifts in the image with Z).
- `sudo` on the Pi **needs a password** (not available to the agent). `dfu-util` needs root. The udev rule for password-less DFU is **not installed** (first attempt had broken quoting; the broken rule file was removed).
- Printer is **user-attended**: the user is at the machine and watches the camera/hand on power switch. Always get an explicit go before any new kind of motion/heating. Interactive style: do safe read-only checks yourself, ask for physical steps.

## Verified working (2026-10-12)
- Klipper v0.13.0-697 on host **and all 3 MCUs** (Octopus reflashed over USB-DFU this session; procedure in README Phase 1). `tools/validate.sh` → 0 fail (only warn = Happy Hare stats in `save_variables.cfg`).
- CAN (`can0` 1 Mbit): toolhead `41b162ca2046`, MMB `691d61df91e5`. Octopus serial `/dev/serial/by-id/usb-Klipper_stm32f446xx_44005F001251303431333234-if00`.
- Sensorless homing: **60 mm/s, SGTHRS 145** (X/Y, back-right corner, endstops at 350). Tuned with `tools/tune_homing_speed.py`: 65 passed, 70 early-stalls on Y (twice), lower SGTHRS made it worse. **Do not change.** A blind SGTHRS change earlier mis-homed the machine and drove it into the front-left corner — never scale SGTHRS blindly; use the tool.
- Z homes at bed centre with TAP; user confirmed physically that Z=0 is correct. TAP PROBE_ACCURACY std-dev ≈ 0.001 mm at 5–20 mm/s.
- QGL: 31 s / 2 passes (was 142 s) after `retry_tolerance 0.0125`, `horizontal_move_z 8`, probe `speed 10`, speed 400. Bed mesh 9×9: 224 s cold (range 0.15 mm cold, never re-run hot). Details in README.
- Travel accel was tested to 8000 mm/s² (max_accel) with `tools/tune_travel_accel.py` (10000 gave a 0.76 mm discrepancy). Travel is speed-capped (400), not accel-capped.
- Camera: Logitech Brio 100, crowsnest → `/webcam/`, registered in Moonraker (`[webcam printer]`), 1280×720.
- Caselight + status LEDs turn on at every Klipper start (`caselight_on_at_startup: True`).
- Phase-0 read-only checks done at 22:02: all temps sane (bed 24 °C, hotend 25.6 °C, chamber 23.5 °C, MCUs 30–46 °C), ADXL345 on the SB2040 returns data, extruder TMC2209 answers (IOIN version 0x21), `QUERY_PROBE` = open.

## Config changes made this session (all committed)
MMB board_pins inlined in `mcu.cfg` (Klippain checkout kept clean); extruder TMC2209 enabled; MMU set to ERCF v2.0 defaults (gear 80:20, 0.5 A; selector 0.4 A; 12 gates; no pre-gate sensors; `.mmu_config` synced); camera/moonraker webcam; **Filametrix cutter enabled** (`form_tip_macro: _MMU_CUT_TIP`); homing/QGL/mesh speed settings; LEDs on at startup.

## Filametrix cutter — enabled but NOT physically verified
- `_MMU_CUT_TIP_VARS` (in `mmu/base/mmu_macro_vars.cfg`): pin touch point **X19 Y20** (user: closest approach without touching), compressed **X6.5 Y20** (old 12.5 mm arm travel kept), start X54, blade_pos 37.5, retract 25, pushback 5, cut speeds 33/8 mm/s, travel 166, safe margin 45/45. Cutter is fixed to the flying gantry → cuts at **any Z**; Y only chooses where on the bed.
- Old tuned values came from repo history (`git show 83a3060:mmu/base/mmu_filametrix.cfg`, pin was 13,19 then).
- **Before the first unload/tool change:** jog by hand (slow, `F1500`) to X54 Y20 → X19 (first touch) → X6.5 (full compression), confirm arm fully compresses and nothing hits. Revert switch: `form_tip_macro : _MMU_FORM_TIP`.

## NOT done yet (this is the work for next session)
Follow README Phase 0 → 5. Status:
1. **Phase 0 remainder:** heater/fan/LED/Nevermore function tests (short, low temp), `QUERY_ENDSTOPS`.
2. **Phase 2 remainder:** nothing critical (home/QGL/TAP all work); re-check TAP z_offset (`-0.375` in `overrides.cfg`, carried over) hot.
3. **Phase 3 — printer calibration (none done):** bed PID, hotend PID (carried-over PIDs), extruder `rotation_distance` (overrides has 44.17 vs Klippain CW2 template 22.68/50:10 — unresolved; needs filament in bypass), Shake&Tune input shaper (current 87.8 2hump_ei / 36.6 mzv are carried over), hot bed mesh, pressure advance, flow.
4. **Phase 4 — MMU (none done):** `MMU_SERVO` (current angles 160/30/130 unvalidated; old install used 115/48/112), `MMU_CALIBRATE_SELECTOR RESET=1` then `AUTO=1` (+ `BYPASS=1`; **stale selector data in `save_variables.cfg`**), gear (gate 0), encoder, gates, bowden (collision method, no toolhead sensor), toolhead dims set by hand (72/8/2 are generic; **hotend model unknown**), cutter verification above, loads/unloads, tool changes 0↔1↔2.
5. **Phase 5:** slicer start G-code (in README), test prints.
- Filament situation: only 2–3 spools at the printer; old buffer has **9 lanes** (gates 9–11 have no buffer lane). README has the "limited filament" plan (offcuts for per-gate calibration, one spool for bowden).
- Open questions for the user: hotend model; whether MMB RGB LED/anything else needs setup; confirm `variable_*` defaults in `variables.cfg` (park/purge positions) — it's still the stock Klippain template.

## Gotchas learned (save yourself time)
- **Bash tool + heredocs:** `\n` inside Python/shell heredocs written through the Bash tool turns into real newlines (broke `tune_homing_speed.py` twice). Create/modify files with the Write/Edit tools, not shell heredocs, whenever strings contain `\n`.
- Auto-mode permission denials occurred on some remote writes/restarts and a few "enable cutter" style actions; when the user says "go", it succeeded. Don't try to bypass a denial — explain and ask.
- `git pull --ff-only` on the Pi fails if `save_variables.cfg` (Happy Hare stats) or a script-edited file is dirty; `git checkout -- <file>` is safe for stats only (but ask first).
- `tools/tune_homing_speed.py` rewrites the managed block in `overrides.cfg` (speed + SGTHRS) on the Pi; commit it after a run.
- **Never run Happy Hare's `./install.sh` / `-i`** (re-renders `mmu/base/*.cfg` from `.mmu_config`). Only `install.sh -f`.
- Klippain's `G28` after a Klipper restart needs Z re-homed; restarts leave Z unhomed and motors idle — park Z high before restart if XY homing tests follow.
- `rtk` in the shell prints "Failed to resolve 'rg'" noise; harmless.
- Stray `~/voron24-klipper` (broken `/home/pi` symlinks) and old `*.old-*`/`printer_config_backup_*` dirs on the Pi are unused.

## Tools (all in `tools/`)
`validate.sh` (read-only health check) · `restore.sh` (rebuild; `--dry-run`) · `backup-calibration.sh [--push]` (commit calibration files) · `tune_homing_speed.py` (homing speed/SGTHRS search with travel+camera checks) · `tune_travel_accel.py` (lost-step accel test) · `system/can0`. Firmware configs in `firmware/` (octopus, mmb, sb2040).
