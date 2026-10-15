#!/usr/bin/env python3
"""Pre-flight safety check for a G-code file before it is sent to the Voron 2.4 (Klippain + Happy Hare).

usage: tools/gcode_lint.py FILE.gcode [--tools 2] [--max-z 300]

Read-only. Exit status 0 = no ERROR, 1 = at least one ERROR. WARNs never fail the run.
Checks: START_PRINT first with the parameters the installed Klippain expects, END_PRINT last,
XYZ inside the build volume, feedrates, temperatures, tool numbers, extrusion sanity,
firmware retraction (G10/G11), forbidden commands (G28, QGL, mesh, M600 ...), unknown commands.
"""
import argparse
import math
import re
import sys

BED_X = (0.0, 350.0)
BED_Y = (0.0, 350.0)
MAX_FEED = 400 * 60            # mm/min, machine travel cap
MAX_ACCEL = 8000               # tested travel limit (tools/tune_travel_accel.py)
WARN_ACCEL = 7000              # X input shaper limit; Y is lower (~3500) but print accel is per-move
MAX_NOZZLE = 260
MAX_BED = 110
FIL_AREA = math.pi * (1.75 / 2) ** 2

REQUIRED_START = ["BED_TEMP", "EXTRUDER_TEMP", "MATERIAL", "INITIAL_TOOL", "TOOLS_USED", "SIZE"]
KNOWN_MATERIALS = {"PLA", "PET", "ABS", "TPU"}          # variable_material_parameters in variables.cfg
FORBIDDEN = {"G28", "QUAD_GANTRY_LEVEL", "BED_MESH_CALIBRATE", "M600", "M601", "SAVE_CONFIG", "FIRMWARE_RESTART",
             "RESTART", "M112", "M999", "SET_KINEMATIC_POSITION", "G92_XYZ", "MMU_RECOVER", "MMU_ERASE_ENDLESS_SPOOL"}
OK_CMDS = {"G0", "G1", "G2", "G3", "G4", "G10", "G11", "G20", "G21", "G90", "G91", "G92", "M82", "M83", "M84", "M104",
           "M106", "M107", "M109", "M140", "M190", "M204", "M220", "M221", "M73", "M117", "M118", "M400",
           "SET_VELOCITY_LIMIT", "SET_PRESSURE_ADVANCE", "SET_PRINT_STATS_INFO", "START_PRINT", "END_PRINT",
           "SET_RETRACTION", "TIMELAPSE_TAKE_FRAME", "EXCLUDE_OBJECT_DEFINE", "EXCLUDE_OBJECT_START",
           "EXCLUDE_OBJECT_END", "M141", "M191", "SET_GCODE_OFFSET", "PAUSE", "RESUME", "CANCEL_PRINT",
           "M900", "M205", "SET_FAN_SPEED", "WIPE_NOZZLE", "CLEAN_NOZZLE"}


def parse_params(rest):
    out = {}
    for tok in rest.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.upper()] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--tools", type=int, default=12, help="number of valid tool numbers (default 12)")
    ap.add_argument("--max-z", type=float, default=300.0)
    ap.add_argument("--max-nozzle", type=float, default=MAX_NOZZLE)
    a = ap.parse_args()

    errors, warns = [], []
    err = lambda n, m: errors.append("line %d: %s" % (n, m))
    warn = lambda n, m: warns.append("line %d: %s" % (n, m))

    x = y = z = e_total = 0.0
    abs_xyz = True
    rel_e = None
    first_cmd = None
    last_cmd = None
    seen_start = False
    tools_seen = []
    layers = 0
    ext_len = 0.0
    e_pos_total = 0.0
    min_z_extrude = None
    max_xy = [1e9, 1e9, -1e9, -1e9]
    max_e_ratio = 0.0
    unknown = {}
    retr_g10 = 0
    manual_retract = 0
    pos_known = False

    with open(a.file, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    for n, raw in enumerate(lines, 1):
        line = raw.split(";", 1)[0].strip()
        if raw.strip().startswith(";LAYER_CHANGE") or raw.strip().startswith(";LAYER:"):
            layers += 1
        if not line:
            continue
        parts = line.split(None, 1)
        cmd = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""
        if first_cmd is None and cmd not in ("G90", "M83", "M82"):
            first_cmd = cmd
        if cmd not in ("M73", "M117", "M118", "M400"):      # progress/status markers may trail END_PRINT
            last_cmd = cmd

        if cmd in FORBIDDEN:
            err(n, "forbidden command %s (Klippain/HH do this in START_PRINT)" % cmd)
            continue

        m = re.fullmatch(r"T(\d+)", cmd)
        if m:
            t = int(m.group(1))
            if not seen_start:
                err(n, "tool change before START_PRINT")
            if t >= a.tools:
                err(n, "tool T%d out of range (0..%d)" % (t, a.tools - 1))
            tools_seen.append(t)
            continue

        if cmd == "START_PRINT":
            if seen_start:
                err(n, "second START_PRINT")
            seen_start = True
            p = parse_params(rest)
            for k in REQUIRED_START:
                if k not in p:
                    err(n, "START_PRINT missing %s" % k)
            if p.get("MATERIAL", "").upper() not in KNOWN_MATERIALS:
                err(n, "START_PRINT MATERIAL=%s unknown (known: %s)" % (p.get("MATERIAL"), sorted(KNOWN_MATERIALS)))
            for k, lim in (("EXTRUDER_TEMP", a.max_nozzle), ("BED_TEMP", MAX_BED)):
                try:
                    v = float(p.get(k, "0"))
                    if not 0 < v <= lim:
                        err(n, "%s=%s outside 1..%g" % (k, p.get(k), lim))
                except ValueError:
                    err(n, "%s not numeric: %s" % (k, p.get(k)))
            if "SOAK" not in p:
                warn(n, "no SOAK= parameter: Klippain default is 8 min bed soak")
            if "CHAMBER" not in p and "CHAMBER_TEMP" in p:
                warn(n, "CHAMBER_TEMP= is ignored by this Klippain; the parameter is CHAMBER=")
            sz = p.get("SIZE", "").split("_")
            try:
                f = [float(v) for v in sz]
                if len(f) != 4 or f[0] >= f[2] or f[1] >= f[3] or f[0] < 0 or f[2] > 350 or f[3] > 350:
                    err(n, "SIZE=%s is not a valid first-layer bounding box" % p.get("SIZE"))
            except ValueError:
                err(n, "SIZE=%s not numeric" % p.get("SIZE"))
            continue

        if cmd == "END_PRINT":
            continue

        if cmd == "G90":
            abs_xyz = True
            continue
        if cmd == "G91":
            abs_xyz = False
            continue
        if cmd == "M82":
            rel_e = False
            continue
        if cmd == "M83":
            rel_e = True
            continue
        if cmd == "G92":
            m = re.search(r"\bE(-?[\d.]+)", rest, re.I)
            if m and not re.search(r"\b[XYZ]", rest, re.I):
                e_total = float(m.group(1))
            elif re.search(r"\b[XYZ]", rest, re.I):
                err(n, "G92 with XYZ (shifts coordinates) is not allowed")
            continue
        if cmd in ("G10", "G11"):
            retr_g10 += 1
            continue

        if cmd == "M106" and re.search(r"\bP[1-9]", rest, re.I):
            warn(n, "M106 with a fan index (%s): the Nevermore is driven by START_FILTER, not M106 P" % rest.strip())
            continue
        if cmd in ("M141", "M191"):
            warn(n, "%s: chamber commands are shimmed to no-ops (slicer_compat.cfg); START_PRINT CHAMBER= does the soak" % cmd)
            continue

        if cmd in ("M104", "M109", "M140", "M190"):
            m = re.search(r"\bS(-?[\d.]+)", rest, re.I)
            if m:
                v = float(m.group(1))
                lim = a.max_nozzle if cmd in ("M104", "M109") else MAX_BED
                if v > lim:
                    err(n, "%s S%g exceeds limit %g" % (cmd, v, lim))
            continue

        if cmd in ("G0", "G1"):
            if not seen_start:
                err(n, "motion before START_PRINT")
            vals = {k: float(v) for k, v in re.findall(r"\b([XYZEF])(-?[\d.]+)", rest, re.I)} if rest else {}
            vals = {k.upper(): v for k, v in vals.items()}
            if "F" in vals and vals["F"] > MAX_FEED:
                err(n, "feedrate F%g exceeds %g mm/min" % (vals["F"], MAX_FEED))
            nx, ny, nz = x, y, z
            if abs_xyz:
                nx, ny, nz = vals.get("X", x), vals.get("Y", y), vals.get("Z", z)
            else:
                nx, ny, nz = x + vals.get("X", 0), y + vals.get("Y", 0), z + vals.get("Z", 0)
            if "X" in vals and not BED_X[0] <= nx <= BED_X[1]:
                err(n, "X%.2f outside %s" % (nx, BED_X))
            if "Y" in vals and not BED_Y[0] <= ny <= BED_Y[1]:
                err(n, "Y%.2f outside %s" % (ny, BED_Y))
            if "Z" in vals and not (0.0 <= nz <= a.max_z):
                err(n, "Z%.2f outside 0..%g" % (nz, a.max_z))
            if "Z" in vals and nz < 0.05:
                err(n, "Z%.3f too low (nozzle into bed)" % nz)
            de = 0.0
            if "E" in vals:
                if rel_e is None:
                    warn(n, "E move before M82/M83 (assuming relative)")
                    rel_e = True
                de = vals["E"] if rel_e else vals["E"] - e_total
                e_total = e_total + vals["E"] if rel_e else vals["E"]
                if abs(de) > 30:
                    err(n, "single extrusion move of %.1f mm filament" % de)
            dist = math.hypot(nx - x, ny - y)
            if de > 0 and dist > 0.05 and ("X" in vals or "Y" in vals):
                ext_len += dist
                e_pos_total += de
                max_e_ratio = max(max_e_ratio, de / dist)
                if de / dist > 0.12:
                    err(n, "extrusion %.3f mm filament per mm path (>0.12: over-extrusion or typo)" % (de / dist))
                min_z_extrude = nz if min_z_extrude is None else min(min_z_extrude, nz)
                max_xy = [min(max_xy[0], nx, x), min(max_xy[1], ny, y), max(max_xy[2], nx, x), max(max_xy[3], ny, y)]
            elif de < -0.0 and dist < 0.05 and "Z" not in vals:
                manual_retract += 1
            if "X" in vals or "Y" in vals or "Z" in vals:
                x, y, z = nx, ny, nz
                pos_known = True
            continue

        if cmd in ("SET_VELOCITY_LIMIT", "M204"):
            # Orca emits these when "Emit limits to G-code" is on: values come from the printer's Motion ability tab
            p = parse_params(rest)
            accels = []
            if cmd == "SET_VELOCITY_LIMIT":
                if "ACCEL" in p:
                    accels.append(p["ACCEL"])
                if "VELOCITY" in p:
                    try:
                        if float(p["VELOCITY"]) > 400:
                            err(n, "SET_VELOCITY_LIMIT VELOCITY=%s exceeds 400 mm/s" % p["VELOCITY"])
                    except ValueError:
                        pass
            else:
                accels += re.findall(r"\b[SPT](\d+(?:\.\d+)?)", rest, re.I)
            for v in accels:
                try:
                    v = float(v)
                except ValueError:
                    continue
                if v > MAX_ACCEL:
                    err(n, "%s sets accel %g mm/s2 (> %g: Motion ability limits are too high?)" % (cmd, v, MAX_ACCEL))
                elif v > WARN_ACCEL:
                    warn(n, "%s sets accel %g mm/s2 (> %g: above the Y input shaper limit)" % (cmd, v, WARN_ACCEL))
            continue

        if cmd == "SET_PRESSURE_ADVANCE":
            warn(n, "slicer sets pressure advance; START_PRINT already applies the material PA")
            continue
        if cmd not in OK_CMDS:
            unknown[cmd] = unknown.get(cmd, 0) + 1

    # whole-file checks
    if not seen_start:
        errors.append("no START_PRINT found")
    elif first_cmd != "START_PRINT":
        warns.append("first command is %s, not START_PRINT" % first_cmd)
    if last_cmd != "END_PRINT":
        errors.append("last command is %s, expected END_PRINT" % last_cmd)
    if ext_len == 0:
        errors.append("no extrusion moves found")
    if layers == 0:
        warns.append("no ;LAYER_CHANGE / ;LAYER: markers found")
    if tools_seen:
        warns.append("tool changes: %s" % " ".join("T%d" % t for t in tools_seen))
    if manual_retract and not retr_g10:
        warns.append("%d slicer-style retract moves and no G10/G11: firmware_retraction is enabled in Klippain, "
                     "set 'use firmware retraction' in the slicer" % manual_retract)
    if unknown:
        warns.append("unrecognised commands (macros?): " + ", ".join("%s x%d" % kv for kv in sorted(unknown.items())))
    if min_z_extrude is not None and min_z_extrude > 0.5:
        warns.append("lowest extrusion at Z%.2f: first layer looks too high" % min_z_extrude)

    print("file: %s (%d lines)" % (a.file, len(lines)))
    print("layers: %d, extruded path: %.0f m, filament (positive E): %.0f mm, bbox X%.1f..%.1f Y%.1f..%.1f"
          % (layers, ext_len / 1000, e_pos_total, max_xy[0], max_xy[2], max_xy[1], max_xy[3]))
    for w in warns:
        print("WARN  " + w)
    for er in errors:
        print("ERROR " + er)
    print("RESULT: %d error(s), %d warning(s)" % (len(errors), len(warns)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
