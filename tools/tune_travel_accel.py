#!/usr/bin/env python3
"""Find the highest XY travel acceleration that does not lose steps (for QGL / bed-mesh moves).

Run ON THE PRINTER'S PI (printer idle, X/Y/Z homed, toolhead at the bed centre, hand on the power switch).
Z is parked at 30 mm so nothing can touch the bed.

For each acceleration step the toolhead runs a fast loop over the QGL/mesh corner area
(50,25 -> 50,275 -> 300,275 -> 300,25) --loops times at --speed mm/s, returns to the centre, and then the
same "travel from centre to wall" check used by tune_homing_speed.py is applied: if the motors skipped
steps during the fast moves, the physical position is not where Klipper thinks it is and the measured
homing travel differs from the expected 170.00 mm.  The webcam centroid check is applied too.
Acceleration is changed at runtime with SET_VELOCITY_LIMIT (nothing is written to the config).

usage: tools/tune_travel_accel.py --yes [--accels 3000,4500,6000,8000,10000] [--speed 400] [--loops 8]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tune_homing_speed as t  # noqa: E402

CORNERS = [(50, 25), (50, 275), (300, 275), (300, 25)]


def pattern(speed, accel, loops):
    f = speed * 60
    lines = ["G90", "SET_VELOCITY_LIMIT ACCEL=%d" % accel]
    for _ in range(loops):
        for x, y in CORNERS:
            lines.append("G1 X%d Y%d F%d" % (x, y, f))
    lines.append("G1 X%g Y%g F%d" % (t.CENTER, t.CENTER, f))
    lines.append("M400")
    t.gcode("\n".join(lines), 300)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accels", default="3000,4500,6000,8000,10000")
    ap.add_argument("--speed", type=float, default=400)
    ap.add_argument("--loops", type=int, default=8)
    ap.add_argument("--tol-mm", type=float, default=0.5)
    ap.add_argument("--px-tol", type=float, default=12)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    accels = [int(x) for x in a.accels.split(",")]

    st = t.query(["configfile", "toolhead", "print_stats"])
    cfg = st["configfile"]["settings"]["stepper_x"]
    mm_per_step = cfg["rotation_distance"] / (cfg["full_steps_per_rotation"] * cfg["microsteps"])
    th = st["toolhead"]
    orig_accel = int(st["configfile"]["settings"]["printer"]["max_accel"])
    t.log("plan: accels %s at %g mm/s, %d loops each; config max_accel=%d" % (accels, a.speed, a.loops, orig_accel))
    if not a.yes:
        t.log("no --yes: not moving anything")
        return 0
    if st["print_stats"]["state"] in ("printing", "paused"):
        raise t.Abort("printer is printing")
    if th["homed_axes"] != "xyz":
        raise t.Abort("home first")
    if abs(th["position"][0] - t.CENTER) > 1 or abs(th["position"][1] - t.CENTER) > 1:
        raise t.Abort("toolhead must be at X175 Y175")

    safe = t.read_block()
    base = None
    best = None
    try:
        t.park_z()
        c0 = t.centroid()
        if c0 == "lost":
            raise t.Abort("camera cannot find toolhead")
        base = c0
        for acc in accels:
            t.log("== accel %d, %g mm/s ==" % (acc, a.speed))
            t0 = time.time()
            pattern(a.speed, acc, a.loops)
            dt = time.time() - t0
            t.gcode("SET_VELOCITY_LIMIT ACCEL=%d" % orig_accel, 30)
            t.log("  pattern took %.1f s" % dt)
            w = [0.0]
            t.trial("X", mm_per_step, a.tol_mm, w)
            t.trial("Y", mm_per_step, a.tol_mm, w)
            t.recenter()
            t.cam_check(base, a.px_tol, "accel %d" % acc)
            best = acc
            t.log("  PASS accel %d (worst deviation %.2f mm)" % (acc, w[0]))
    except t.Abort as e:
        t.log("  FAIL:", e)
        t.log("-- recovery: back to %g mm/s homing, full G28" % safe[0])
        try:
            t.gcode("SET_VELOCITY_LIMIT ACCEL=%d" % orig_accel, 30)
        except t.Abort:
            pass
        try:
            t.recover(safe, base, a.px_tol)
        except t.Abort as e2:
            t.log("!!! recovery failed:", e2, "- physical position UNKNOWN, inspect the machine")
            return 2
    except KeyboardInterrupt:
        t.log("interrupted - check the machine")
        return 130
    t.log("======== RESULT: highest passing travel accel = %s (speed %g) ========" % (best, a.speed))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except t.Abort as e:
        t.log("!!!", e)
        sys.exit(2)
