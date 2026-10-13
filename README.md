# voron24 — Klipper config for a Voron 2.4 (350) with ERCF v2 MMU

Klipper configuration, restore tooling and the full bring-up/calibration checklist for **voron24**
(`ssh jd@voron24.jerrettdavis.com`, Mainsail on port 80).

| | |
|---|---|
| Printer | LDO Voron 2.4 350 mm kit, CoreXY, 4× Z + QGL, Stealthburner + Clockwork 2, Voron TAP |
| Boards | BTT Octopus (main, USB) · Mellow SB2040 v1 (toolhead, CAN) · BTT MMB CAN v1.0 (MMU, CAN) |
| MMU | ERCF **v2.0**, 12 gates ("carrot" blocks), LinearServoSelector, encoder, bypass, **no** toolhead/pre-gate sensors |
| Filament cutter | [Filametrix](https://github.com/sorted01/Filametrix) toolhead cutter (blade on the Stealthburner, pressed by a depressor pin on the gantry/frame) — via Happy Hare's built-in `_MMU_CUT_TIP` |
| Host | Raspberry Pi (`voron24`), Raspberry Pi OS Bookworm, CAN via USB-CAN adapter (`can0`, 1 Mbit) |
| Config framework | [Klippain](https://github.com/Frix-x/klippain) (pinned in `.VERSION`) + [Happy Hare](https://github.com/moggieuk/Happy-Hare) v4 |
| Camera | Logitech Brio 100 (USB) → Crowsnest/ustreamer → Mainsail |

> **State as of 2026-10-12:** software stack up and `Printer is ready`; **nothing is calibrated yet**.
> Work through [Setup & calibration](#setup--calibration-in-order) top to bottom. Items in
> [Open items](#open-items--verify-before-trusting-the-config) are config values that were reviewed
> but need a physical check.

---

## Contents

1. [Repo layout & how the config fits together](#repo-layout--how-the-config-fits-together)
2. [Wiring / MCU map](#wiring--mcu-map)
3. [Open items — verify before trusting the config](#open-items--verify-before-trusting-the-config)
4. [Setup & calibration, in order](#setup--calibration-in-order)
5. [Camera](#camera)
6. [Slicer setup](#slicer-setup)
7. [Maintenance: updates, backups, restore, validation](#maintenance-updates-backups-restore-validation)
8. [Troubleshooting](#troubleshooting)

---

## Repo layout & how the config fits together

This repo **is** `~/printer_data/config` on the Pi (`origin` = `JerrettDavis/voron24-klipper`).

| Path | What it is | Edit? |
|---|---|---|
| `printer.cfg` | Entry point: Klippain feature includes (kinematics, TAP, fans, MMU …) | yes |
| `mcu.cfg` | **All wiring**: MCU serial/CAN IDs, TMC driver includes, `[board_pins]` aliases, toolhead pin remaps | yes |
| `overrides.cfg` | Per-machine tuning: PIDs, SGTHRS, probe z_offset, input shaper, extruder rotation_distance, fans | yes |
| `variables.cfg` | Klippain macro variables (park positions, soak, MMU start/end behaviour). Currently stock template | yes |
| `moonraker.conf` | Moonraker incl. update manager, `[mmu_server]`, `[webcam printer]` | yes |
| `crowsnest.conf` | Camera stream (device by stable `/dev/v4l/by-id/…` path) | yes |
| `mmu/base/mmu_hardware_unit0.cfg` | Happy Hare hardware: MCU `unit0`, steppers, TMC, servo, encoder | yes (see warning) |
| `mmu/base/mmu_parameters_unit0.cfg`, `mmu_macro_vars.cfg`, `mmu.cfg` | Happy Hare behaviour (speeds, homing, sync, toolhead dims, macros) | yes |
| `mmu/.mmu_config` | Happy Hare installer's saved answers (Kconfig). Hand-synced with the files above | careful |
| `save_variables.cfg` | **Live** Happy Hare store: calibration results (selector offsets, servo angles, gear rotation distances, bowden length, encoder resolution) | written by Klipper |
| `mmu/mmu_vars.cfg` | Happy Hare's template store — **unused** here (Klippain's `[save_variables]` in `variables.cfg` points at `save_variables.cfg` and wins) | no |
| `firmware/` | Klipper `make menuconfig` configs for the MMB and SB2040 (see [Firmware](#phase-1--firmware)) | reference |
| `tools/` | `validate.sh`, `restore.sh`, `backup-calibration.sh`, `system/can0` | yes |
| `config/ macros/ moonraker/ scripts/` | **Symlinks** into `~/klippain_config` (Klippain itself). Git-ignored. Don't edit through them | **never** |

**Rules that keep upgrades safe**

* Klippain upstream (`~/klippain_config`) must stay **unmodified**. Everything custom lives in the files
  above. `tools/validate.sh` fails if the checkout is dirty. (Previously the MMB pin map was hand-edited
  inside it; it is now inlined in `mcu.cfg`.)
* `mmu/base/*.cfg` are *generated* by Happy Hare's `install.sh` from `mmu/.mmu_config`, then hand-edited here.
  **Do not run `./install.sh` or `./install.sh -i`** to “fix” things — it re-renders them from `.mmu_config`
  and can silently revert reviewed values (gear ratio, currents, sensors). If you must upgrade Happy Hare
  with the installer, run it, then `git diff` and restore anything it changed. `tools/restore.sh` only uses
  `install.sh -f` (re-link only).
* Commit calibration results: `tools/backup-calibration.sh [--push]` (see [Backups](#backups--calibration-snapshots)).

---

## Wiring / MCU map

**MCUs** (`mcu.cfg`)

| Name in Klipper | Board | Link | ID |
|---|---|---|---|
| `mcu` | BTT Octopus (STM32F446) | USB | `/dev/serial/by-id/usb-Klipper_stm32f446xx_44005F001251303431333234-if00` |
| `toolhead` | Mellow SB2040 v1 (RP2040) | CAN | `canbus_uuid: 41b162ca2046` |
| `unit0` | BTT MMB CAN v1.0 (STM32G0B1) | CAN | `canbus_uuid: 691d61df91e5` (declared in `mmu/base/mmu_hardware_unit0.cfg`) |

**Toolhead (SB2040) pin remaps** (`mcu.cfg`): extruder step/dir/en/heater/thermistor, TAP (`probe`, `^toolhead:PROBE_INPUT`),
part fan (`FAN0`), hotend fan (`FAN1`), toolhead cooling fan (`FAN2`, in `overrides.cfg`), status LEDs (`RGB`),
ADXL345 on the board, extruder TMC2209 UART (`toolhead:E_TMCUART`).

**MMB CAN v1.0 pin map** (raw pins in `mmu/base/mmu_hardware_unit0.cfg`; aliases in `mcu.cfg`):

| Function | Pin | Note |
|---|---|---|
| Gear: step/dir/en/UART/DIAG | PB15 / PB14 / !PA8 / PA10 / PA3 | M1 (DIAG = STP1) |
| Selector: step/dir/en/UART/DIAG | PD2 / PB13 / !PD1 / PC7 / PA4 | M2 (DIAG = STP2) |
| Selector endstop | `^PB2` | STP11 |
| Servo | PA0 | `MOT` |
| Encoder | `^PA1` | `SENSOR` |
| Pre-gate sensors | PB9 PB8 PC15 PC13 PC14 PB12 PB11 PB10 | STP3–STP10 — **not fitted**, left empty in config |

The MMB has only 11 STP inputs and 3 are taken (2 DIAG + selector endstop), so at most 8 of the 12 gates
could ever have a pre-gate sensor.

**Known pin-alias quirks** (harmless today, remember them before using the aliases):
* `mcu.cfg` maps `TOOLHEAD_SENSOR` **and** `PROBE_INPUT` to `MCU_5V_ENDSTOP`, and `EXTRUDER_SENSOR` to `MCU_FAN2`
  (already used by `toolhead_fan`). Don't enable a Happy Hare toolhead/extruder sensor without re-pinning.
* Sensorless X/Y homing (`SGTHRS 145`) uses the Octopus DIAG pins; the toolhead X endstop line is commented out.

---

## Open items — verify before trusting the config

These came out of a review of the freshly-installed config against Happy Hare v4 and the physical hardware.
Tick them off as you go; the calibration sections reference them.

- [x] **Klippain checkout was modified** (`BTT_MMB_CAN_v1.0.cfg`: `mcu: mmu → unit0`). Fixed: block inlined in `mcu.cfg`, checkout reverted.
- [x] **Extruder TMC2209 wasn't configured** (no `[tmc2209 extruder]`; driver ran on power-on defaults). Fixed: enabled via Klippain `TMC2209.cfg` + `uart_pin: toolhead:E_TMCUART`; verified with `DUMP_TMC STEPPER=extruder REGISTER=IOIN` (TMC2209, `version=0x21`). Klippain default is `run_current: 0.45` — confirm against your motor.
- [x] **MMU stepper settings were ERCF v3.0 defaults on a v2.0 unit** (gear 1:1 / 0.8 A, selector 0.7 A; `.mmu_config` also said 3.0 / 8 gates). Set to HH's ERCF v2.0 defaults: gear ratio **80:20**, gear **0.5 A** (hold 0.1), selector **0.4 A**; `.mmu_config` synced (v2.0, 12 gates).
  *If the gear behaves weakly/loudly, the 80:20 ratio is the first thing to check against your actual gear set.*
- [x] **Pre-gate sensors** configured on pins where nothing is wired → removed (empty pins). Re-enable only if you add sensors (gates 0–7 max).
- [x] **Camera**: now by stable by-id path, 1280×720 MJPG @ 15 fps, registered in Moonraker (`[webcam printer]`).
- [ ] **Octopus firmware is older (`v0.12.0-93`) than the host and the other MCUs (`v0.13.0-697`).** Reflash it ([Firmware](#phase-1--firmware)) before first print.
- [ ] **Servo angles** (`mmu_parameters_unit0.cfg`: up 160 / down 30 / move 130) are *not* HH's ERCF defaults (30 / 100 / 50 in `.mmu_config`). They only apply until you calibrate with `MMU_SERVO`; verify direction/travel **with no filament and the selector clear** before anything else.
- [ ] **Stale MMU state in `save_variables.cfg`** from earlier experiments (selector offsets, bypass offset 273.7, statistics). Treat as uncalibrated: step 4.2 resets and redoes the selector.
- [ ] **Toolhead dimensions** (`mmu.cfg [mmu_toolhead default]`: extruder→nozzle 72, entry→extruder 8, residual 2) are generic, and `.mmu_config` says toolhead *Other/Unknown*. Confirm your hotend; HH has presets under `~/Happy-Hare/installer/toolheads/Kconfig.stealthburner_clockwork2_*` (Revo 72/13/2, Dragon HF 70.3/12.4/30.6, Rapido HF 84.8/13/5 …) — or measure (step 4.7).
- [ ] **Filametrix cutter** vars are Happy Hare defaults, unmeasured, and inactive (`form_tip_macro` still `_MMU_FORM_TIP`); see step 4.7b before enabling.
- [ ] **No toolhead/extruder sensor.** `MMU_CALIBRATE_TOOLHEAD` homes to the toolhead sensor, so it can't run; set dimensions manually. Extruder homing uses the encoder (collision) — expected for ERCF without a sensor.
- [ ] **Extruder `rotation_distance: 44.1737` in `overrides.cfg`** is carried over from the old setup, while Klippain's CW2 template uses `22.6789511` with `gear_ratio 50:10` and `microsteps: 32` (override sets 16). Recalibrate (step 3.8) rather than trust it.
- [ ] **Carried-over tuning** (PID, input shaper `87.8/2hump_ei` & `36.6/mzv`, TAP `z_offset −0.375`, `SGTHRS 145`) came from the previous install — re-measure, don't assume.
- [ ] `variables.cfg` is the unmodified Klippain template (park positions, soak times, `mmu_*` flags, purge). Review once.
- [ ] A stray clone `~/voron24-klipper` exists on the Pi with broken `/home/pi/...` symlinks. It is unused; delete it when convenient (`rm -rf ~/voron24-klipper`). Old `*.old-*`, `mmu.old-*` and `~/printer_config_backup_*` copies are safe to remove once you're happy.

---

## Setup & calibration, in order

General rules: **hands near the power switch**, bed clear, first moves slow. Add `HELP=1` to any Happy Hare
command (e.g. `MMU_CALIBRATE_GEAR HELP=1`) to see its parameters and examples. Run
`tools/validate.sh` on the Pi at the start of every phase; it is read-only.

**Power-on behaviour:** on every Klipper start (i.e. every machine power-on) Klippain's `_INIT_LEDS` turns the caselight on at `light_intensity_startup` (100 %) and sets the status LEDs to `READY` — enabled by `variable_caselight_on_at_startup: True` in `variables.cfg`. Intensities while printing/at end are `light_intensity_printing: 30`, `light_intensity_end_print: 0`.

### Phase 0 — Pre-flight (no motion)

1. `ssh jd@voron24.jerrettdavis.com` → `~/printer_data/config/tools/validate.sh`. Expected: no `FAIL`. Known `WARN`: Octopus firmware version until step 1.
2. In Mainsail confirm: Klipper `ready`, three MCUs (`mcu`, `toolhead`, `unit0`) with no errors, temperatures sane (bed, hotend, chamber, MCUs).
3. Heaters: set hotend to 50 °C, bed to 40 °C briefly; verify temperatures **rise** and are attributed to the right heater; cool down. (Do before any long heating.)
4. Fans: `SET_FAN_SPEED FAN=…` / Mainsail fan sliders — part fan, hotend fan (`heater_fan` should spin when hot), toolhead cooling fan, controller fan, Nevermore filter.
5. LEDs/neopixels: caselight and status LEDs should come on by themselves after a Klipper restart (see Power-on behaviour); MMB RGB light separately.
6. Camera: Mainsail dashboard should show the stream ([Camera](#camera)).
7. Extruder driver: `DUMP_TMC STEPPER=extruder REGISTER=IOIN` returns a reply (`version=0x21`).

### Phase 1 — Firmware

Do this **now**, before motion tests, so every MCU runs the same Klipper as the host.

`tools/validate.sh` compares each MCU's `mcu_version` with the host. Current: Octopus `v0.12.0-93-g43a9685c`;
SB2040 & MMB `v0.13.0-697-g430a2a8a0` = host.

* **Octopus (USB, STM32F446)** — `~/klipper$ make menuconfig` with: *STM32F446*, bootloader offset **32 KiB**, clock **12 MHz crystal**, communication **USB (on PA11/PA12)**. Then `make -j4`, stop Klipper, flash via your bootloader method (Katapult over USB or DFU), start Klipper. The exact Octopus `.config` wasn't saved previously; after flashing, save it as `firmware/octopus-f446.config`.
* **SB2040 (CAN)** — config saved in `firmware/sb2040-toolhead.config` (RP2040, CAN, 1 Mbit).
* **MMB CAN v1.0 (CAN)** — config saved in `firmware/mmb-can-v1.0.config` (STM32G0B1, 8 MHz crystal, 8 KiB bootloader offset, CAN on PB0/PB1, 1 Mbit).

Flash a CAN node (as done for the MMB):

```bash
cd ~/klipper
make KCONFIG_CONFIG=/home/jd/printer_data/config/firmware/mmb-can-v1.0.config -j4   # build with the saved config
sudo systemctl stop klipper
python3 ~/katapult/scripts/flash_can.py -i can0 -q                                   # list nodes (bootloader UUIDs)
python3 ~/katapult/scripts/flash_can.py -i can0 -f ~/klipper/out/klipper.bin -u 691d61df91e5
sudo systemctl start klipper
```

*Query CAN UUIDs (Klipper stopped):* `python3 ~/klipper/scripts/canbus_query.py can0`. Expected: `41b162ca2046` (toolhead) and `691d61df91e5` (MMB).

`can0` is brought up by `/etc/network/interfaces.d/can0` (copy in `tools/system/can0`: 1 Mbit, `txqueuelen 1024`). A mismatched bitrate on any node = `Timeout on connect`.

### Phase 2 — Printer mechanical & electrical (first motion, slow)

1. **Endstops/QUERY**: `QUERY_ENDSTOPS` (open/triggered), press TAP's nozzle (`QUERY_PROBE`): flips when triggered. Check **before** homing.
2. **Motor directions & buzz**: `STEPPER_BUZZ STEPPER=stepper_x` (also `stepper_y`, `stepper_z`, `z1`, `z2`, `z3`). All Z buzzes should move the same direction visually; `stepper_z1`/`z3` directions are inverted in `overrides.cfg` (`!Z1_DIR`, `!Z3_DIR`) — confirm that matches how your Z motors are mounted.
**Sensorless homing speed (tuning notes, 2026-10-12).** Current: `homing_speed 60` (Klippain default is 40; set in the managed block in `overrides.cfg`), `driver_SGTHRS 145` for X and Y (unchanged), home corner = **back right** (both endstops at 350). A trial at 60 mm/s with `SGTHRS 215` (scaled proportionally) **mis-homed**: the stall fired early, Klipper believed it was at 350/350 while the toolhead was mid-bed, and the following moves/Z-probing drove the toolhead into the **front-left** corner. Reverted (`ba4c2de`). Then raised speed only (SGTHRS kept at 145) with `tools/tune_homing_speed.py`: **50, 55, 60 and 65 mm/s all passed** (3 X+Y cycles each; travel from the bed centre to the wall always 169.8–170.2 mm vs the expected 170.0 mm; camera within ~1.5 px), but **70 mm/s early-stalled on Y** (travelled 169.1 mm vs 170.0 — script stopped, no further motion). **60 mm/s was chosen** (10 mm/s margin below the failure) and stress-tested with 10 more X+Y cycles (20 homes: travel 169.80–170.19 mm, no camera drift). Rules for further tuning:
1. Change **one** thing at a time (speed *or* SGTHRS), one axis at a time, with a hand on the power switch and the camera up; stop at the first sign of a wrong stop.
2. Do **not** scale SGTHRS blindly. Higher SGTHRS = more sensitive = false early triggers (especially during the acceleration ramp). Tune per Klipper's TMC docs (lower SGTHRS until the axis homes reliably, then add margin).
3. After each trial home, verify the *physical* position (camera / by hand) matches Klipper before trusting it — repeated-home motor counters are not a position check.
4. 255 is the TMC2209 max; practical ceiling is roughly 50–60 mm/s on this machine.

3. **Home**: `G28 X`, then `G28 Y` (sensorless, `SGTHRS 145`; tune per Klipper's TMC docs if it stalls early/late or crashes), then `G28 Z` (TAP). Keep a hand on the switch.
4. **TAP**: `PROBE_ACCURACY` (std dev ≲ 0.005 mm), then `PROBE_CALIBRATE`/`Z_OFFSET_APPLY_PROBE` → sets `[probe] z_offset` (currently `−0.375`; save into `overrides.cfg`). Heat nozzle to print temp for the final offset (TAP is nozzle-contact).
5. **Gantry level**: `QUAD_GANTRY_LEVEL` (350 mm config). Repeat until the final retry is ≲ 0.005 mm.

**Homing speed search tool** (`tools/tune_homing_speed.py`, run on the Pi, printer idle + homed + toolhead at X175 Y175, hand on the power switch): `tools/tune_homing_speed.py --yes [--max 70] [--step 5] [--cycles 3]`. It raises only `homing_speed` (managed block in `overrides.cfg`), restarts Klipper per speed, and after *every single home* checks (1) real travel from the stepper counters equals the distance Klipper assumes (an early stall makes it shorter), (2) both CoreXY motors agree, (3) the webcam still sees the toolhead where it was in the baseline (teal-pixel centroid, ±12 px; baseline is taken at Z30 because Z shifts the toolhead in the overhead image). On the first failure it stops moving, restores the last good speed and restarts Klipper — then **inspect the machine; the physical position is unknown**. Use `--dry-run` to see the plan.

### Phase 3 — Printer calibration

Order matters — each step depends on the previous.

1. **Bed PID**: `PID_CALIBRATE HEATER=heater_bed TARGET=100` → `SAVE_CONFIG` or copy into `overrides.cfg` (`pid_kp/ki/kd`). `max_power: 0.75` is set for the bed.
2. **Hotend PID**: `PID_CALIBRATE HEATER=extruder TARGET=250` (part fan on, as in printing) → copy into `overrides.cfg`.
3. **Chamber soak sanity**: confirm `Chamber` temperature sensor reading plausible values.
4. **Extruder rotation_distance** *(unrelated to the MMU gear)*: with filament loaded directly (bypass), heat, mark 120 mm above the extruder entry, extrude 100 mm slowly (`G1 E100 F60`), measure remaining; `new = old × actual/100`. Put into `overrides.cfg` `[extruder] rotation_distance`. Also reconcile with the CW2 template (open item).
5. **Input shaper (Shake&Tune)**: verify `ACCELEROMETER_QUERY` works (ADXL on SB2040), then `AXES_SHAPER_CALIBRATION` and `COMPARE_BELTS_RESPONSES`; apply to `[input_shaper]` in `overrides.cfg`. Reports land in `~/printer_data/config/ShakeTune_results` (not tracked). Also run `CREATE_VIBRATIONS_PROFILE` once for speed/accel limits.
6. **Bed mesh**: heated, after QGL: `BED_MESH_CALIBRATE` (Klippain adaptive mesh).
7. **Pressure advance**: `PRESSURE_ADVANCE_CALIBRATION` (Klippain macro) per filament; store per filament in the slicer.
8. **Flow**: `FLOW_MULTIPLIER_CALIBRATION` (Klippain macro) per filament.
9. Snapshot: `tools/backup-calibration.sh "chore: printer calibration"`.

### Phase 4 — MMU (ERCF v2, Happy Hare v4)

Prerequisites: Phase 3.4 done (extruder drive known-good), Octopus/MMB firmware current, bowden tube cut and connected to the extruder entry, **filament not yet inserted** except where stated. `MMU_STATUS` currently reports required steps **`MMU_CALIBRATE_ENCODER`** and **`MMU_CALIBRATE_BOWDEN`** (it reads the old stored selector data as present — don't trust that, see 4.2).

Check/adjust first: [Open items](#open-items--verify-before-trusting-the-config) (gear ratio, servo angles, toolhead dims).

### Historical values (2023 install, for sanity-checking only)

From repo history (`git show 83a3060:...`, 9-gate ERCF v2 on this same printer). **Not applied** except the cutter block; use them to spot a calibration that came out wildly different:

| Item | Old value | Current state |
|---|---|---|
| Gear `rotation_distance` (gate 0) | 22.5906 | uncalibrated (22.7317 default) |
| Encoder resolution | 0.9475 | uncalibrated (placeholder 1.0) |
| Bowden length | 1027.6 mm | uncalibrated (unit0 `-1`) |
| Servo up / down / move | 115 / 48 / 112 | 160 / 30 / 130 (not validated) |
| Gear ratio / run current | 80:20 / 1.0 A (selector 0.4 A) | 80:20 / 0.5 A (selector 0.4 A) — if the gear is weak, 1.0 A is what ran before |
| Toolhead extruder→nozzle / sensor→nozzle | 60 / 55 | 72 / 8 entry (unmeasured) |
| Extruder homing | collision, current 40 %, `extruder_homing_max 120` | encoder collision, current 30 % |
| `sync_to_extruder` / `sync_gear_current` | 1 / 80 % | 0 / 100 % — enable after basic loads work |
| Per-gate encoder multipliers | 0.98–1.007 | uncalibrated |
| Extruder `rotation_distance` | 44.1737 | same (carried over) |

### Calibrating with limited filament (2–3 spools, 9-lane buffer)

You do **not** need 12 spools to calibrate. Only **one** thing needs a full spool path (the bowden), and `variable_bowden_lengths: 0` means one bowden length serves all gates.

| Calibration | What it needs | Notes |
|---|---|---|
| Servo, selector, bypass position (4.1–4.2) | **No filament** | Do all gates for free |
| Gear `rotation_distance` gate 0 (4.3) | ~250 mm of filament in gate 0 | Reference gate |
| Encoder (4.4) | ≥ 450 mm free filament beyond gate 0 (spool or loose length) | `MMU_CALIBRATE_ENCODER LENGTH=200 REPEATS=5` needs only ~250 mm if space is tight |
| Other gates (4.5) | ~250 mm **offcut** in each gate, *not* a spool | Run `MMU_CALIBRATE_GATE GATE=n` per gate (or `ALL=1` with offcuts everywhere). Uncalibrated gates keep the default until done — they're usable, just less accurate |
| Bowden (4.6) | One spool, gate 0, bowden connected to the extruder | Single value for all gates |
| Toolhead / cutter (4.7–4.7b) | One loaded gate | Use the same spool |

Practical plan: put your 2–3 spools in gates **0, 1, 2** (buffer lanes 1–3). Put **≥ 300 mm offcuts** in the remaining gates only for the gate-calibration pass, then pull them. The old buffer has 9 lanes, so gates **9–11 have no buffer lane**: either feed them from a spool direct (not recommended — tangles/drag skew the encoder) or leave them unused/unspooled until a 12-lane buffer exists. Calibration of those three gates can still be done with offcuts. Re-run `MMU_CALIBRATE_GATE GATE=n` for a gate when you first load a different filament type/brand in it.

**Order that minimises filament handling**
1. No filament: 4.0 → 4.1 servo → 4.2 selector (+ bypass).
2. Spool A in gate 0 (+ buffer): 4.3 gear → 4.4 encoder → 4.6 bowden.
3. Toolhead (4.7), cutter measurements (4.7b).
4. Offcuts into gates 1–11 one by one (or ALL=1): 4.5.
5. 4.8 loads/unloads on gates 0–2 with real spools; 4.9 tool changes **0↔1↔2** only — enough to prove tip-cut, purge and sync behaviour.
6. `tools/backup-calibration.sh --push "chore: MMU calibration"`.
7. Test print with 2–3 colours (Phase 5).

**4.0 Sanity (no filament)**
* `MMU_STATUS` → ERCF v2.0, 12 gates, LinearServoSelector.
* `MMU_TEST_CONFIG` and `MMU_HELP` to see the command set.
* `DUMP_TMC STEPPER=…`: for MMU drivers use the stepper object names `mmu_stepper unit0_gear` / `unit0_selector`.
* Selector microswitch: `QUERY_ENDSTOPS` should list the selector endstop; press by hand → toggles.
* Encoder: `MMU_ENCODER` / push filament through by hand later; `Encoder reads` should change.

**4.1 Servo** — `MMU_SERVO POS=up`, `POS=move`, `POS=down` (add `HELP=1`). Up = lever releases filament, down = gear grips. Adjust the angles for your servo/arm and `MMU_SERVO POS=… SAVE=1` (stored in `save_variables.cfg`). Verify nothing binds at the end of travel (listen for servo buzz).

**4.2 Selector** — start from a clean slate: `MMU_CALIBRATE_SELECTOR RESET=1`. Then `MMU_CALIBRATE_SELECTOR AUTO=1` with gate 0 selected (uses the selector endstop; for 12 gates you may need `GATE=…`/`EXTRAPOLATE=1` per `HELP=1`). Then `MMU_CALIBRATE_SELECTOR BYPASS=1` for the bypass position. Verify: `MMU_SELECT GATE=0`, `GATE=5`, `GATE=11`, `MMU_SELECT_BYPASS` — selector should centre on each lane. `MMU_HOME` afterwards.

**4.3 Gear stepper** — gate 0, filament inserted into the gate: `MMU_CALIBRATE_GEAR` (moves 100 mm; measure the actual move and rerun with `MEASURED=<mm>`). With `variable_rotation_distances: 1`, this value is for gate 0 (the reference).

**4.4 Encoder** — `MMU_CALIBRATE_ENCODER` (gate 0; default 3 × 400 mm; needs ~1 m of free filament path). Result → `mmu_calibration_0` in `save_variables.cfg` (currently placeholder `1.0`).

**4.5 Other gates** — load filament in gates, then `MMU_CALIBRATE_GATES ALL=1` (calibrates each gate's gear rotation distance against the encoder reference). Optional but recommended with 12 individually-measured gates.

**4.6 Bowden length** — `MMU_CALIBRATE_BOWDEN` with gate 0 selected, bowden connected, filament in gate. With no toolhead sensor this uses **collision with the extruder gears via the encoder** (add `COLLISION=1` or `MANUAL=1` if HH asks; `BOWDEN_LENGTH=<approx>` if bowden is longer than the default search). `bowden_homing_max` is 2000 mm.

**4.7 Toolhead dimensions** — no sensor → set manually in `mmu/base/mmu.cfg` `[mmu_toolhead default]`:
`toolhead_extruder_to_nozzle`, `toolhead_entry_to_extruder`, `toolhead_residual_filament`. Measure extruder-gear→nozzle by marking filament on a cold nozzle (extruder gears → melt zone), or start from the matching HH preset and tune with `MMU_TEST_LOAD`/ test prints. Then `RESTART`.

**4.7b Filametrix cutter** — Happy Hare v4 has native support for this cutter-by-motion design (`mmu/macros/mmu_cut_tip.cfg`; its docs even use Filametrix as the example, cutting along X toward Xmin). The Filametrix page's own `additional.cfg` is **not needed** — don't add it alongside HH's macro.

Config state: the `[gcode_macro _MMU_CUT_TIP_VARS]` block is in `mmu/base/mmu_macro_vars.cfg` (and `CONFIG_MMU_HAS_TOOLHEAD_CUTTER=y` in `.mmu_config`), pre-filled with the **values from the previously tuned install** (repo history, commit `83a3060`, 2023-12-20): pin at X13 Y19, park +35 mm (start X48), fully compressed X0.5 — **re-measured now: pin X19 Y20, compressed X6.5 Y20, start X54**, blade 37.5 mm, retract 25, pushback 5, rip 1 mm, fast/slow cut 33/8 mm/s, travel 166 mm/s, safe margin 45/45. **The cutter is ENABLED**: `form_tip_macro : _MMU_CUT_TIP` in `mmu/base/mmu.cfg` (+ `.mmu_config`), `force_form_tip_standalone : 1`. Every unload / tool change now drives the toolhead to the pin. Measured on the rebuilt toolhead: X19 Y20 is the closest the toolhead gets without the arm touching, so `pin_loc_xy = 19, 20`; compressed point `6.5, 20` keeps the old 12.5 mm of arm travel. Start (X54,Y20) and the safety waypoint (X99,Y65) are all inside the printer limits (X/Y 0–350). The depressor pin is fixed to the **flying gantry**, so the cut works at **every Z height** — no Z move is needed (Happy Hare's 1 mm `park_toolchange` z-hop is fine). Contact depends on X only; Y just chooses *where on the bed* the cut happens (`pin_loc_xy` Y = 20, the front edge). During a print the toolhead therefore travels to Y20/X≤99 at print height +1 mm: keep prints out of that front-left strip, or change the Y in `pin_loc_xy`/`pin_loc_compressed_xy` (both must match) to a clear spot, e.g. a rear Y. To turn it back off: `form_tip_macro : _MMU_FORM_TIP`. Do this before the first unload:

1. Mechanical (per the Filametrix page): blade is a type-4 hobby scalpel blade cut to 26 mm; the knife holder must slide up/down without friction; the depressor on the gantry must line up with the depression on the cutting arm. Home, then jog by hand at low speed (`G1 X.. Y.. F1500`) to find where the arm *just touches* the depressor pin → this is **`pin_loc_xy`** (old install: `13, 19`; should match what you find). Keep jogging until fully compressed, leaving a few mm from the frame → **`pin_loc_compressed_xy`**. Cut direction is X toward Xmin (`cutting_axis: 'x'`, `pin_park_dist` positive).
2. Re-measure nozzle-tip→blade distance → **`blade_pos`** (old install: 37.5). **`retract_length`** must be < `blade_pos` (old: 25), **`pushback_length`** ≈ PTFE length + 3 mm (old: 5; HH default 15). Also set the toolhead dimensions in step 4.7 (`toolhead_ooze_reduction` residual is subtracted from `retract_length`).
3. If anything differs from the pre-filled values, edit them in `mmu/base/mmu_macro_vars.cfg` and `RESTART`. Keep a hand on the switch for the first cuts.
4. Test cold-safe first: with filament loaded and hot, run `MMU_TEST_FORM_TIP` (HH runs the cut macro). Watch the first cuts at slow speed; raise `cut_fast_move_speed` only if the cut is clean. Check the filament end: clean cut, no nail-head left in the heat break; increase `pushback_length` if loads jam. If cuts are partial, raise `cut_iterations` or `cut_stepper_current` (≤150 %).
5. Clog/clean-up: cut fragments are pushed back into the hotend (`pushback_length`); a blade-life counter warns after `variable_cutter_blade_limit` (3000) cuts.
6. Gantry-servo variant (`gantry_servo_enabled`) is *not* used here (the Filametrix page's servo section is "tbd").

**4.8 First loads/unloads** — `MMU_SELECT GATE=0`, `MMU_PRELOAD`, `MMU_LOAD` (hot nozzle, ≥ min extrude temp), `MMU_UNLOAD`. Watch for grinding, slipping at the encoder, and the servo timing. Do the same on bypass (`MMU_SELECT_BYPASS`, `MMU_LOAD`).

**4.9 Tool change test** — `T1` then `T0` etc. with cold-safe temperatures set, with the purge bucket/Blobifier area clear (Klippain/HH purge macros are active). Run `MMU_CHECK_GATE` to refresh gate map.

**4.10 Behaviour tuning (after it works)** — `sync_to_extruder`, `flowguard_*`, `tip forming` (`_MMU_FORM_TIP` vars in `mmu_macro_vars.cfg`; `MMU_TEST_FORM_TIP`), purge volumes. Leave Spoolman off until the MMU is stable (`spoolman_support: off`).

Snapshot: `tools/backup-calibration.sh --push "chore: MMU calibration"`.

### Phase 5 — First prints

1. Single-colour print from **bypass**, then from gate 0 via the MMU.
2. Slicer: see [Slicer setup](#slicer-setup). Multi-colour test with 2 tools, then more.
3. Keep `variable_mmu_check_gates_on_start_print: False` until `TOOLS_USED=!referenced_tools!` is in the slicer start gcode, then set it to `True`.

---

## Camera

* Hardware: Logitech Brio 100 on the Pi's USB. Crowsnest runs `ustreamer`, nginx proxies it at `/webcam/`.
* `crowsnest.conf [cam 1]`: device `/dev/v4l/by-id/usb-046d_Brio_100_2502APELK228-video-index0` (stable across reboots; `index0` is the capture node), `1280x720` MJPG, `15 fps`, port `8080`.
* `moonraker.conf [webcam printer]`: `mjpegstreamer`, stream `/webcam/?action=stream`, snapshot `/webcam/?action=snapshot`, 16:9 — appears automatically in Mainsail (Settings → Webcams shows it as config-sourced).
* Verified: snapshot `1280x720`, HTTP 200. Test: `curl -s -o /tmp/s.jpg -w '%{http_code}\n' http://voron24.jerrettdavis.com/webcam/?action=snapshot`.
* The Brio 100 also does 1920×1080 MJPG; raise `resolution:` if the Pi CPU allows. Flip/rotate in Mainsail's webcam settings (or `rotation:`/`flip_*:` in the Moonraker section).
* If the stream dies: `sudo journalctl -u crowsnest -n 50`; `v4l2-ctl --list-devices`; replug USB; `sudo systemctl restart crowsnest`.
* **Viewing angle:** the camera is a bird's-eye view of the bed, so it shows X/Y motion well but **cannot judge Z height or nozzle-to-bed gap**. Don't use it to confirm Z; use `QUERY_PROBE`/TAP and paper/feeler checks. (Z=0 was confirmed physically at the machine on 2026-10-12 — still re-run Phase 2.4 after any TAP/nozzle change.) It is good for watching the cutter run, tool changes and first-layer progress remotely.
* Timelapse (`moonraker-timelapse` is present on the Pi) can reuse the same snapshot URL; not enabled in this config yet.

---

## Slicer setup

Klippain `START_PRINT` takes (names as read from the macro): `BED_TEMP`, `EXTRUDER_TEMP`, `CHAMBER_TEMP`, `MATERIAL`, `SIZE` (first-layer bbox for adaptive mesh), `INITIAL_TOOL`, `TOOLS_USED`.

PrusaSlicer/OrcaSlicer start G-code (single tool):

```gcode
START_PRINT BED_TEMP=[first_layer_bed_temperature] EXTRUDER_TEMP=[nozzle_temperature_initial_layer] CHAMBER_TEMP=[chamber_temperature] MATERIAL={filament_type[initial_tool]} SIZE={first_layer_print_min[0]}_{first_layer_print_min[1]}_{first_layer_print_max[0]}_{first_layer_print_max[1]} INITIAL_TOOL={initial_tool} TOOLS_USED=!referenced_tools!
```

(Adjust placeholders to your slicer's variable names — Orca uses `{first_layer_print_min[0]}` style similarly.) End G-code: `END_PRINT`.

Printer profile for the MMU: single extruder, multi-material **tool change G-code `T[next_extruder]`**, no purge tower from the slicer if you use HH's purge, `Toolchange` handled by Happy Hare (`mmu_server.enable_file_preprocessor: True`, `enable_toolchange_next_pos: True` in `moonraker.conf`). Per Klippain docs, `TOOLS_USED=!referenced_tools!` is required for the gate pre-check.

---

## Maintenance: updates, backups, restore, validation

### Validate (read-only, any time)

```bash
~/printer_data/config/tools/validate.sh
```

Checks: services, `can0` (up, 1 Mbit), all three MCUs + firmware vs host, Klipper `ready`, Happy Hare enabled & 12 gates,
Klippain symlinks/checkout clean, which `save_variables` file is live, webcam registered + snapshot returns a 1280×720 JPEG. Exit 1 on any `FAIL`.

### Making config changes

1. Edit on the Pi (Mainsail editor) or in this repo and `git pull` on the Pi. 2. `RESTART` (or `FIRMWARE_RESTART` for MCU changes) and check Mainsail shows `Printer is ready`. 3. Run `tools/validate.sh`. 4. Commit (`tools/backup-calibration.sh` for calibration files, otherwise `git commit`) and `git push`. Never edit through the Klippain symlinks.

### Updates

* Klipper, Moonraker, Mainsail, Crowsnest, Klippain Shake&Tune, Happy Hare update through **Mainsail → Machine → Update Manager** (Happy Hare and Shake&Tune have entries in `moonraker.conf`).
* After a **Klipper** update, reflash MCUs whose firmware drifts from the host (Phase 1).
* After a **Klippain** update: `git -C ~/klippain_config status` must stay clean; `.VERSION` records the commit this config was built against.
* After a **Happy Hare** update: Klipper may complain about config changes. Compare with `~/Happy-Hare/config/base/*.cfg`, merge changes by hand; don't run the interactive installer blindly (see rules above).

### Backups & calibration snapshots

```bash
~/printer_data/config/tools/backup-calibration.sh --push "chore: calibration snapshot"
```

Commits `save_variables.cfg`, `overrides.cfg`, `mmu/.mmu_config`, `mmu/base`, `printer.cfg`, `mcu.cfg`. Run it after every calibration phase.
Firmware configs are in `firmware/`. Camera/Moonraker settings are in `crowsnest.conf`/`moonraker.conf` (nothing lives only in the Mainsail UI database).

### Restore (fresh Pi / broken tree)

1. Install base stack with KIAUH: Klipper, Moonraker, Mainsail, Crowsnest (+ `can-utils`, optional Shake&Tune venv deps via its Moonraker entry).
2. `sudo cp tools/system/can0 /etc/network/interfaces.d/can0 && sudo ifup can0` (or `tools/restore.sh can0`).
3. Move any default `~/printer_data/config` aside, then `git clone https://github.com/JerrettDavis/voron24-klipper ~/printer_data/config`.
4. `~/printer_data/config/tools/restore.sh all` — clones Klippain/Happy Hare if missing, re-links Klippain symlinks and Happy Hare modules (`install.sh -f` only), installs `can0`, restarts services (Klipper only if idle). Use `--dry-run` first.
5. Reflash MCUs if blank (Phase 1) and run `tools/validate.sh`.

`tools/restore.sh` steps: `klippain`, `happyhare`, `links`, `can0`, `services`, `all`.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `Timeout on connect` for `toolhead` / `unit0` | `ip -d link show can0` (1 Mbit, UP); `candump can0`; `canbus_query.py can0` (Klipper stopped); node powered; terminator jumpers (one at each end of the bus) |
| `Unknown pin chip name 'mmu'` or alias errors in MMU config | `mcu.cfg` must define the MMB aliases against `mcu: unit0`; don't re-add the Klippain `BTT_MMB_CAN_v1.0.cfg` include |
| MCU firmware version mismatch warning | Phase 1 reflash |
| MMU `Selector is NOT HOMED` / lost position | `MMU_HOME` (filament out of the selector path first); if offsets are wrong re-run 4.2 |
| Grinding at gate / encoder doesn't count | Servo angles (`MMU_SERVO`), encoder wiring (`^PA1`), `MMU_CALIBRATE_ENCODER` |
| HH config values revert after an update | The installer re-rendered from `.mmu_config`; `git diff` and restore |
| `Printer is ready` but no webcam | `crowsnest` journal; device path; `/server/webcams/list` should list `printer` |
| Klipper `Config error` after editing | `sudo journalctl -u klipper -n 50` / Mainsail error; `git diff`; `git checkout -- <file>` |

Useful commands: `MMU_STATUS`, `MMU_STATS`, `MMU_SENSORS`, `MMU_GATE_MAP`, `MMU_REMAP_TTG`, `MMU_RECOVER`, `MMU_MOTORS_OFF`, `MMU_UNLOCK`, `MMU_HELP`.
