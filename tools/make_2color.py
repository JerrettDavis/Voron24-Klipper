"""Derive a two-colour test from an OrcaSlicer single-colour G-code: insert T1 at the start of a given layer.

usage: make_2color.py IN.gcode OUT.gcode [--layer 9]

Only two edits are made to the slicer output: the START_PRINT line gains SYNC_MMU_EXTRUDER=1 (what the updated preset emits)
and `T1` is inserted right after the layer-change block of the chosen layer, exactly where Orca puts a filament change.
"""
import argparse
import re

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("dst")
ap.add_argument("--layer", type=int, default=9)
a = ap.parse_args()

lines = open(a.src, encoding="utf-8").read().split("\n")
out = []
did_start = did_t1 = False
for l in lines:
    if l.startswith("START_PRINT ") and not did_start:
        if "SYNC_MMU_EXTRUDER" not in l:
            l = l.replace(" MATERIAL=", " SYNC_MMU_EXTRUDER=1 MATERIAL=", 1)
        did_start = True
    out.append(l)
    if l.strip() == "SET_PRINT_STATS_INFO CURRENT_LAYER=%d" % a.layer and not did_t1:
        out.append("; CHANGE_FILAMENT (post-processed: colour change at layer %d)" % a.layer)
        out.append("T1")
        did_t1 = True
assert did_start and did_t1, "start line or layer marker not found"
open(a.dst, "w", encoding="utf-8", newline="\n").write("\n".join(out))
print("wrote", a.dst, "T1 at layer", a.layer)
