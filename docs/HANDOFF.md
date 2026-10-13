# Handoff — voron24 bring-up (written 2026-10-12 ~22:05 CDT; updated end of session ~23:40 CDT)

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

- **Phase 0 complete (2026-10-12 22:15):** hotend 50 °C / bed 40 °C reached and attributed correctly (hotend 25→~52 in ~25 s with ~2 °C overshoot; bed 24→40 in ~70 s at max_power 0.75); hotend fan 100 % and toolhead fan 80 % came on when hot; part fan, Nevermore (`fan_generic filter`), controller fan confirmed spinning by user; caselight + status LEDs on. `QUERY_ENDSTOPS`: XYZ open (mid-bed), `mmu_gear_touch`/`mmu_sel_home`/`mmu_sel_touch` read TRIGGERED with no filament (recheck in 4.0). MMU gear/selector TMC2209 answer (use `STEPPER=unit0_gear` / `unit0_selector`). No tach on any fan (rpm None).

- **MMU servo + selector done (2026-10-12 22:55, no filament):** servo angles **up 160 / down 30 / move 125** (`servo_move_angle: 125` in `mmu/base/mmu_parameters_unit0.cfg`; 130 snagged at gates 6–7, 112 dragged at the far end, 135 stalls instantly). Servo whines briefly at the start/end of a move (0.4 s PWM burst) — normal. **Selector offsets were measured BY HAND**, not AUTO: gate 0 = 0.0, gate 11 = 259.8, bypass = 274.4 → pitch ≈ 23.6 mm, written to `save_variables.cfg` (`[0.0, 23.6, 47.2, 70.9, 94.5, 118.1, 141.7, 165.3, 188.9, 212.6, 236.2, 259.8]`, bypass 274.4). These match the original stored values. `MMU_CALIBRATE_SELECTOR AUTO=1` gave 22.5 mm (run while the arm was dragging, travel 261.6) and 23.1 mm (travel 269.6) pitches that left gates misaligned and snagged everywhere — **don't use AUTO on this machine**; to redo: `MMU_HOME`, `GATE=0`, `MMU_MOTORS_OFF`, slide to gate 11 by hand, `GATE=11`, then `BYPASS=1` (HH refuses to save bypass if it exceeds `cad_selector_tolerance`+limit, and refuses to extrapolate when gate 0 = 0.0, so edit the offsets by hand). Sweep gates 5/6/7/11/bypass/0 verified smooth and centred by the user; tiny rub at gate 11 (may need light sanding).

## Config changes made this session (all committed)
MMB board_pins inlined in `mcu.cfg` (Klippain checkout kept clean); extruder TMC2209 enabled; MMU set to ERCF v2.0 defaults (gear 80:20, 0.5 A; selector 0.4 A; 12 gates; no pre-gate sensors; `.mmu_config` synced); camera/moonraker webcam; **Filametrix cutter enabled** (`form_tip_macro: _MMU_CUT_TIP`); homing/QGL/mesh speed settings; LEDs on at startup.

## Filametrix cutter — enabled but NOT physically verified
- `_MMU_CUT_TIP_VARS` (in `mmu/base/mmu_macro_vars.cfg`): pin touch point **X19 Y20** (user: closest approach without touching), compressed **X6.5 Y20** (old 12.5 mm arm travel kept), start X54, blade_pos 37.5, retract 25, pushback 5, cut speeds 33/8 mm/s, travel 166, safe margin 45/45. Cutter is fixed to the flying gantry → cuts at **any Z**; Y only chooses where on the bed.
- Old tuned values came from repo history (`git show 83a3060:mmu/base/mmu_filametrix.cfg`, pin was 13,19 then).
- **Before the first unload/tool change:** jog by hand (slow, `F1500`) to X54 Y20 → X19 (first touch) → X6.5 (full compression), confirm arm fully compresses and nothing hits. Revert switch: `form_tip_macro : _MMU_FORM_TIP`.

## NOT done yet (this is the work for next session)
Follow README Phase 0 → 5. Status (updated end of session 2026-10-12/13):
1. **Phase 0: DONE.** **Phase 2:** nothing critical left; re-check TAP z_offset (`-0.375` in `overrides.cfg`, carried over) with a hot bed.
2. **Phase 3 so far:**
   - **Bed PID DONE** (100 °C): `49.474 / 1.527 / 400.736` (was 38.473/1.110/333.276) → `overrides.cfg`, loaded.
   - **Hotend PID DONE** (250 °C, part fan 50 %): `27.601 / 1.786 / 106.609` (was 28.688/1.821/122.960) → `overrides.cfg`, loaded.
   - **Extruder DONE (2026-10-13):** direction was reversed → `dir_pin: !toolhead:E_DIR` (`mcu.cfg`). `rotation_distance` **22.27** (was 44.1737), verified at 210 °C: 100 mm commanded → exactly 100 mm moved (20 mm of the 120 mm mark remaining). Formula is `new = old × actual_moved / 100` (the old handoff had it inverted). Readings scatter ±1–2 mm, so passes were averaged. **PLA is still in the extruder** (hand-fed, bypass); heaters and motors are off — cold-pull/retract it before MMU steps.
   - **Still to do:** Shake&Tune input shaper (current 87.8 2hump_ei / 36.6 mzv are carried over), hot bed mesh, pressure advance, flow.
3. **Phase 4 so far:** servo + selector DONE (see "MMU servo + selector done" above). **Still to do:** gear (gate 0), encoder, gates, bowden (collision method, no toolhead sensor), toolhead dims by hand (**hotend = Dragon HF/UHF** — confirm which, then measure extruder-gear→nozzle; 72/8/2 are generic), Filametrix cutter hand-jog verification (BEFORE first unload), loads/unloads, tool changes 0↔1↔2. Also recheck the `mmu_gear_touch`/`mmu_sel_touch` TRIGGERED reading in `QUERY_ENDSTOPS` with no filament, and `MMU_STATUS` still lists MMU_CALIBRATE_ENCODER/BOWDEN as required.
4. **Phase 5:** slicer start G-code (in README), test prints.
- Filament situation: only 2–3 spools at the printer; old buffer has **9 lanes** (gates 9–11 have no buffer lane). README has the "limited filament" plan (offcuts for per-gate calibration, one spool for bowden).
- Open questions for the user: whether MMB RGB LED/anything else needs setup; confirm `variable_*` defaults in `variables.cfg` (park/purge positions) — it's still the stock Klippain template.

## Gotchas learned (save yourself time)
- **Bash tool + heredocs:** `\n` inside Python/shell heredocs written through the Bash tool turns into real newlines (broke `tune_homing_speed.py` twice). Create/modify files with the Write/Edit tools, not shell heredocs, whenever strings contain `\n`.
- Auto-mode permission denials occurred on some remote writes/restarts and a few "enable cutter" style actions; when the user says "go", it succeeded. Don't try to bypass a denial — explain and ask.
- `git pull --ff-only` on the Pi fails if `save_variables.cfg` (Happy Hare stats) or a script-edited file is dirty; `git checkout -- <file>` is safe for stats only (but ask first).
- `tools/tune_homing_speed.py` rewrites the managed block in `overrides.cfg` (speed + SGTHRS) on the Pi; commit it after a run.
- **Never run Happy Hare's `./install.sh` / `-i`** (re-renders `mmu/base/*.cfg` from `.mmu_config`). Only `install.sh -f`.
- Klippain's `G28` after a Klipper restart needs Z re-homed; restarts leave Z unhomed and motors idle — park Z high before restart if XY homing tests follow.
- **Applying calibration values:** edit `overrides.cfg` (Edit tool) → commit/push → `git stash; git pull --ff-only; git stash pop` on the Pi → `POST /printer/restart`. Don't use `SAVE_CONFIG`. The Pi's `save_variables.cfg` is always dirty (HH stats), and `tools/backup-calibration.sh --push` on the Pi creates commits ahead of your local clone — `git pull --rebase` locally before pushing.
- **`ANGLE=` on `MMU_SERVO` is ignored and `SAVE=1` saves HH's last commanded angle** — set servo angles in `mmu_parameters_unit0.cfg` (+ `MMU_SERVO RESET=1` and restart), not with MMU_SERVO.
- Auto-mode denied a sed edit of `save_variables.cfg` over ssh until the user explicitly approved it via the question tool — ask first for hand edits of HH vars.
- Use the Grep tool, not `grep` through Bash, for patterns with `\|` (the rtk wrapper mangles them). Complex multi-line ssh quoting broke once; write a script file with the Write tool and pipe it into `ssh … 'python3 -'`.
- `rtk` in the shell prints "Failed to resolve 'rg'" noise; harmless.
- Stray `~/voron24-klipper` (broken `/home/pi` symlinks) and old `*.old-*`/`printer_config_backup_*` dirs on the Pi are unused.

## Tools (all in `tools/`)
`validate.sh` (read-only health check) · `restore.sh` (rebuild; `--dry-run`) · `backup-calibration.sh [--push]` (commit calibration files) · `tune_homing_speed.py` (homing speed/SGTHRS search with travel+camera checks) · `tune_travel_accel.py` (lost-step accel test) · `system/can0`. Firmware configs in `firmware/` (octopus, mmb, sb2040).
