# OrcaSlicer profile for this printer (Voron 2.4 350 + ERCF v2 + Klippain + Happy Hare 4)

**Status (2026-10-14): generated, NOT yet validated by an actual slice.** The OrcaSlicer CLI rejected the files
(`Slic3r::CLI::run found error`, no detail), so import them in the GUI (File > Import > Import Configs) and check each
setting below. Always run `python tools/gcode_lint.py FILE.gcode` on the output before sending it to the printer.

Files: `machine.json`, `process.json`, `filament.json` (built from the stock Voron 2.4 350 / 0.20 standard / Generic PLA
profiles by `tools/make_orca_profile.py`), `test_box_25mm.stl` (25 x 25 x 3.2 mm, centred on the bed).

## What the installed config requires (read from the live printer, not the stock profile)
- **Machine start G-code** (Klippain `START_PRINT`; the chamber parameter is `CHAMBER`, not `CHAMBER_TEMP`):
  `START_PRINT BED_TEMP=[bed_temperature_initial_layer_single] EXTRUDER_TEMP=[nozzle_temperature_initial_layer] CHAMBER=0 SOAK=0 MATERIAL={filament_type[initial_tool]} SIZE={first_layer_print_min[0]}_{first_layer_print_min[1]}_{first_layer_print_max[0]}_{first_layer_print_max[1]} INITIAL_TOOL={initial_tool} TOOLS_USED=!referenced_tools! TOTAL_LAYER=[total_layer_count]`
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
