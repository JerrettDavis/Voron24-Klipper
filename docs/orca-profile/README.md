# OrcaSlicer profile for this printer (Voron 2.4 350 + ERCF v2 + Klippain + Happy Hare 4)

**Status (2026-10-14): generated, NOT yet validated by an actual slice.** The OrcaSlicer CLI rejected the files
(`Slic3r::CLI::run found error`, no detail), so import them in the GUI (File > Import > Import Configs) and check each
setting below. Always run `python tools/gcode_lint.py FILE.gcode` on the output before sending it to the printer.

Files: `machine.json`, `process.json`, `filament.json` (built from the stock Voron 2.4 350 / 0.20 standard / Generic PLA
profiles by `tools/make_orca_profile.py`), `test_box_25mm.stl` (25 x 25 x 3.2 mm, centred on the bed).

## What the installed config requires (read from the live printer, not the stock profile)
- **Machine start G-code** (Klippain `START_PRINT`; the chamber parameter is `CHAMBER`, not `CHAMBER_TEMP`):
  `START_PRINT BED_TEMP=[bed_temperature_initial_layer_single] EXTRUDER_TEMP=[nozzle_temperature_initial_layer] CHAMBER=[chamber_temperature] SOAK=0 MATERIAL={filament_type[initial_tool]} SIZE={first_layer_print_min[0]}_{first_layer_print_min[1]}_{first_layer_print_max[0]}_{first_layer_print_max[1]} INITIAL_TOOL={initial_tool} TOOLS_USED=!referenced_tools! TOTAL_LAYER=[total_layer_count]`
  Without `SOAK=` Klippain soaks the bed for 8 min (`print_default_soak`). `MATERIAL` must be one of PLA / PET / ABS / TPU
  (`variable_material_parameters`), which also sets pressure advance (PLA 0.0525, uncalibrated carry-over) and
  retraction at print start.
- **End G-code:** `END_PRINT` (retract, hot nozzle wipe, heaters off, MMU unload on end).
- **Firmware retraction is enabled** (`firmware_retraction_enabled`, `[firmware_retraction]` in Klipper): tick
  "Use firmware retraction" so the slicer emits `G10`/`G11`; `START_PRINT` sets the length from the material (PLA 0.75).
- **Tool change G-code:** `T[next_extruder]`. Happy Hare does the tip form, cut, unload, load and purge. In the slicer turn OFF:
  prime/wipe tower, ramming, cooling moves, loading/unloading moves and retraction on filament change; pass no purge volume.
- **No other heating or homing commands:** `START_PRINT` homes, levels (QGL), meshes (adaptive from `SIZE`) and wipes by itself.
- `!referenced_tools!` is replaced by the Happy Hare file preprocessor on upload (`[mmu_server] enable_file_preprocessor`).
- Limits: Z max 310 (profile uses 300), accel Y <= 3500 (input shaper MZV 35.8 Hz), X up to ~7000, travel 400 mm/s.
- Layer change G-code sets `SET_PRINT_STATS_INFO CURRENT_LAYER`.
- Do not add `SET_PRESSURE_ADVANCE` in the slicer; the material table owns it until it is calibrated.

## Differences from the old 2023 preset ("Voron 2.4r2 350 0.4 nozzle", ERCF v1.3b / Happy Hare v3)
The old preset is still in `%APPDATA%\OrcaSlicer\user\<id>\machine`. Do not reuse its G-code as is:
- `change_filament_gcode` used `T[next_extruder] STANDALONE=1 CHECK_ONLY=1` and `_SET_LOC_AFTER_TOOLCHANGE`. The installed
  Happy Hare v4 defines `T0..T11` as plain `MMU_CHANGE_TOOL TOOL=n` and `_SET_LOC_AFTER_TOOLCHANGE` no longer exists
  (it would raise "Unknown command"). Use `T[next_extruder]`.
- Start G-code had no `SOAK=`/`TOTAL_LAYER=`; the new one adds `SOAK=0` (else an 8 min bed soak) and `TOTAL_LAYER`, and keeps `CHAMBER=[chamber_temperature]`.
- Chamber and filtration: the printer has a chamber sensor and the Nevermore (`fan_generic filter`). Keep "Support controlling chamber
  temperature" and "Support air filtration" on. Klippain does the chamber soak from `START_PRINT CHAMBER=` and starts the Nevermore with
  `START_FILTER` at the material's `filter_speed` (PLA 0, ABS 80 in `variables.cfg`; stays on 600 s after the print). `slicer_compat.cfg`
  defines no-op `M141`/`M191` so slicer-emitted chamber commands cannot stop a print. Leave the filament's own air-filtration option off (it would emit `M106 P3`).
- Machine accel limits were 15000-20000; the installed input shapers (X EI 63.2 Hz, Y MZV 35.8 Hz) limit Y to ~3500, X to ~7000.
- Retraction was slicer-side (0.3 mm); the installed Klippain enables firmware retraction (G10/G11, length from the material table).
- Process "MMU" variant enabled the prime tower; for the no-purge test it is off.

## Next
Import the three JSONs (or edit the old preset), slice `test_box_25mm.stl`, run `tools/gcode_lint.py` on the result, then upload.
For the 2-colour test: add a filament change (T1) at the layer you want in the slicer (or paint the top layers).

## Machine time cost (Basic information > Time cost = 0.90 $/h)
From `3dprint4me/lib/print-estimation/pricing-policy.js` `machineEconomics()` with the machine basis changed from the default $1000 to $2400
(everything else unchanged: 3 yr life, 10%/yr maintenance, 32 h/week x 52 weeks x 80% utilisation = 1331 productive h/yr, 0.20 kW at $0.15/kWh, 10% failure reserve):

| | $/h |
|---|---:|
| Depreciation ($2400 / 3 yr / 1331 h) | 0.601 |
| Maintenance (10% of basis per year) | 0.180 |
| Electricity (0.20 kW) | 0.030 |
| Base | 0.811 |
| **Per successful hour (/ 0.9)** | **0.901** |

Sensitivity: 0.30 kW average power gives 0.918; a 5 year life gives 0.634. The repo default machine ($1000) is 0.395. Filament cost stays at the repo's PLA fallback of $20/kg.
