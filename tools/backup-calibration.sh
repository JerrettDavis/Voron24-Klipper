#!/usr/bin/env bash
# Commit the files that hold *calibration results* so a restore/reflash doesn't lose them.
#   usage: tools/backup-calibration.sh [--push] ["commit message"]
# What carries calibration:
#   save_variables.cfg                 Happy Hare store (selector offsets, servo angles, gear rotation
#                                      distances, bowden lengths, encoder resolution, stats).
#                                      This is the LIVE file - not mmu/mmu_vars.cfg.
#   mmu/.mmu_config, mmu/base/*.cfg    toolhead params that MMU_CALIBRATE_TOOLHEAD SAVE=1 may write
#   overrides.cfg                      PID, input shaper, probe z_offset, SGTHRS, extruder rotation_distance
set -eu
CFG="${CFG:-$HOME/printer_data/config}"
push=0
if [ "${1:-}" = "--push" ]; then push=1; shift; fi
msg="${1:-chore: calibration snapshot $(date +%F)}"
cd "$CFG"
git add save_variables.cfg overrides.cfg mmu/.mmu_config mmu/base printer.cfg mcu.cfg
if git diff --cached --quiet; then
  echo "Nothing to commit - calibration files unchanged."
  exit 0
fi
git diff --cached --stat
git commit -m "$msg"
if [ "$push" = 1 ]; then git push origin HEAD; fi
