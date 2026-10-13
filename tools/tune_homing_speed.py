#!/usr/bin/env python3
"""Progressively raise sensorless X/Y homing speed and stop at the first sign of a bad home.

Run ON THE PRINTER'S PI, printer idle, X/Y/Z homed and toolhead at the bed centre (175,175), with a hand
on the power switch.  It never touches SGTHRS - only `homing_speed`.

How a bad home is detected (checked after EVERY single homing move, before any further motion):
  1. Travel from the centre to the wall, measured from the TMC stepper step counters (GET_POSITION "mcu:"),
     must equal the distance Klipper *believes* it travelled (toolhead position after the home - 175).
     An early stall trigger makes the real travel shorter than the position Klipper then assumes.
  2. Both CoreXY motors must have moved by the same number of steps in the expected directions.
  3. After re-centring, the webcam must still see the toolhead where it was in the baseline snapshot
     (teal toolhead centroid, +/- --px-tol pixels).  Needs numpy + Pillow (present on the Pi).

Speeds are tried in order  start, start+step, ... up to --max.  Each new speed is written to the managed
block in overrides.cfg, Klipper is RESTARTed, then --cycles X+Y homing pairs are checked.  On the first
failure the script stops moving, restores the last good speed in overrides.cfg and restarts Klipper.
The physical toolhead position is then UNKNOWN: inspect the machine before homing again.

usage:  tools/tune_homing_speed.py --yes [--max 70] [--step 5] [--cycles 3] [--tol-mm 0.5] [--px-tol 12] [--dry-run]
"""
import argparse
import io
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MR = "http://127.0.0.1:7125"
SNAP = "http://127.0.0.1/webcam/?action=snapshot"
CFG = "/home/jd/printer_data/config/overrides.cfg"
BEGIN = "# >>> homing-speed (managed by tools/tune_homing_speed.py)"
END = "# <<< homing-speed"
CENTER = 175.0
SAFE_Z = 30.0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class Abort(Exception):
    pass


def http(url, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise Abort("HTTP %s from %s: %s" % (e.code, url.split("?")[0], e.read()[:300]))
    except Exception as e:  # noqa: BLE001
        raise Abort("request failed %s: %s" % (url.split("?")[0], e))


def gcode(script, timeout=180):
    http(MR + "/printer/gcode/script", urllib.parse.urlencode({"script": script}).encode(), timeout)


def query(objs):
    q = "&".join(urllib.parse.quote(o) for o in objs)
    return json.loads(http(MR + "/printer/objects/query?" + q))["result"]["status"]


def counters():
    gcode("GET_POSITION", 30)
    msgs = json.loads(http(MR + "/server/gcode_store?count=12"))["result"]["gcode_store"]
    for m in reversed(msgs):
        t = re.sub(r"<[^>]+>", "", m["message"])
        mt = re.search(r"mcu: stepper_x:(-?\d+) stepper_y:(-?\d+)", t)
        if mt:
            return int(mt.group(1)), int(mt.group(2))
    raise Abort("could not read stepper counters")


def wait_ready(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if json.loads(http(MR + "/printer/info", timeout=5))["result"]["state"] == "ready":
                return
        except Abort:
            pass
        time.sleep(2)
    raise Abort("Klipper did not return to ready")


def restart():
    log("RESTART Klipper")
    try:
        http(MR + "/printer/restart", b"", 20)
    except Abort:
        pass
    time.sleep(8)
    wait_ready()
    time.sleep(3)


def read_speed():
    s = open(CFG, encoding="utf-8").read()
    m = re.search(re.escape(BEGIN) + r".*?homing_speed:\s*([\d.]+)", s, re.S)
    if not m:
        raise Abort("managed block not found in overrides.cfg")
    return float(m.group(1))


def write_speed(speed):
    s = open(CFG, encoding="utf-8").read()
    block = "%s\n[stepper_x]\nhoming_speed: %g\n\n[stepper_y]\nhoming_speed: %g\n%s" % (BEGIN, speed, speed, END)
    s2, n = re.subn(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _m: block, s, flags=re.S)
    if n != 1:
        raise Abort("managed block not found in overrides.cfg")
    open(CFG, "w", encoding="utf-8", newline="").write(s2)


def centroid():
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    im = np.asarray(Image.open(io.BytesIO(http(SNAP, timeout=15))).convert("RGB")).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    m = (r < 110) & (g > 130) & (b > 130) & (abs(g - b) < 70) & (g - r > 60)
    roi = np.zeros_like(m)
    roi[185:560, 330:1000] = True
    m &= roi
    if m.sum() < 1500:
        return "lost"
    ys, xs = np.nonzero(m)
    return float(xs.mean()), float(ys.mean())


def cam_check(base, px_tol, what):
    if base is None:
        log("  camera check skipped (numpy/Pillow missing)")
        return None
    c = centroid()
    if c == "lost" or c is None:
        raise Abort("%s: toolhead not found by camera (expected near %.0f,%.0f)" % (what, *base))
    d = ((c[0] - base[0]) ** 2 + (c[1] - base[1]) ** 2) ** 0.5
    log("  camera: toolhead at (%.0f,%.0f), %.1f px from baseline" % (c[0], c[1], d))
    if d > px_tol:
        raise Abort("%s: toolhead is %.1f px from where it should be (limit %g) - looks mis-homed" % (what, d, px_tol))
    return c


def trial(axis, mm_per_step, tol_mm):
    a = counters()
    gcode("G28 " + axis, 120)
    b = counters()
    pos = query(["toolhead"])["toolhead"]["position"]
    idx = 0 if axis == "X" else 1
    dx, dy = b[0] - a[0], b[1] - a[1]
    exp = pos[idx] - CENTER
    got = abs(dx) * mm_per_step
    sign_ok = (dx > 0 and dy > 0) if axis == "X" else (dx > 0 and dy < 0)
    pair_ok = abs(abs(dx) - abs(dy)) * mm_per_step <= tol_mm
    log("  G28 %s: motors dA=%+d dB=%+d  travel=%.2f mm  Klipper expects %.2f mm  (home pos %.2f)" %
        (axis, dx, dy, got, exp, pos[idx]))
    if not sign_ok:
        raise Abort("G28 %s: motor directions wrong (dA=%+d dB=%+d)" % (axis, dx, dy))
    if not pair_ok:
        raise Abort("G28 %s: motors disagree (dA=%+d dB=%+d)" % (axis, dx, dy))
    if abs(got - exp) > tol_mm:
        raise Abort("G28 %s: travelled %.2f mm but Klipper assumes %.2f mm (diff %.2f > %.2f) - EARLY/LATE STALL" %
                    (axis, got, exp, got - exp, tol_mm))
    return got


def recenter():
    gcode("G90\nG1 X%g Y%g F9000\nM400" % (CENTER, CENTER), 60)


def cycles(n, mm_per_step, tol_mm, base, px_tol, speed):
    for i in range(1, n + 1):
        trial("X", mm_per_step, tol_mm)
        trial("Y", mm_per_step, tol_mm)
        recenter()
        cam_check(base, px_tol, "cycle %d @ %g mm/s" % (i, speed))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max", type=float, default=70, help="highest speed to try (mm/s)")
    ap.add_argument("--step", type=float, default=5)
    ap.add_argument("--cycles", type=int, default=3, help="X+Y home pairs per speed")
    ap.add_argument("--tol-mm", type=float, default=0.5)
    ap.add_argument("--px-tol", type=float, default=12)
    ap.add_argument("--yes", action="store_true", help="confirm: hand on the switch, bed clear, toolhead at centre")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    st = query(["configfile", "toolhead", "print_stats"])
    cfg = st["configfile"]["settings"]["stepper_x"]
    mm_per_step = cfg["rotation_distance"] / (cfg["full_steps_per_rotation"] * cfg["microsteps"])
    th = st["toolhead"]
    cur = read_speed()
    log("current homing_speed %g mm/s, %.6f mm/step, homed=%r pos=%s" % (cur, mm_per_step, th["homed_axes"], th["position"][:3]))
    speeds = []
    s = cur + a.step
    while s <= a.max + 1e-9:
        speeds.append(s)
        s += a.step
    log("plan: baseline at %g, then %s" % (cur, speeds))
    if a.dry_run or not a.yes:
        log("dry run / no --yes: not moving anything")
        return 0
    if st["print_stats"]["state"] in ("printing", "paused"):
        raise Abort("printer is printing")
    if th["homed_axes"] != "xyz":
        raise Abort("home first (G28) and leave the toolhead at the centre")
    if abs(th["position"][0] - CENTER) > 1 or abs(th["position"][1] - CENTER) > 1:
        raise Abort("toolhead must be at X175 Y175 (is %s)" % th["position"][:2])

    good = cur
    try:
        log("== baseline at %g mm/s ==" % cur)
        c0 = centroid()
        if c0 == "lost":
            raise Abort("camera cannot find the toolhead at the centre")
        base = c0
        if base:
            log("  baseline toolhead pixel position (%.0f,%.0f)" % base)
        cycles(a.cycles, mm_per_step, a.tol_mm, base, a.px_tol, cur)
        for sp in speeds:
            log("== trying %g mm/s ==" % sp)
            t = query(["toolhead"])["toolhead"]
            if "z" in t["homed_axes"] and t["position"][2] < SAFE_Z:
                gcode("G90\nG1 Z%g F600\nM400" % SAFE_Z, 120)   # restart leaves Z unhomed - park it high first
            recenter()
            cam_check(base, a.px_tol, "pre-restart")
            write_speed(sp)
            restart()
            cycles(a.cycles, mm_per_step, a.tol_mm, base, a.px_tol, sp)
            good = sp
            log("  PASS %g mm/s" % sp)
    except Abort as e:
        log("!!! STOP:", e)
        log("!!! No further motion. Restoring homing_speed %g in overrides.cfg and restarting Klipper." % good)
        write_speed(good)
        try:
            restart()
        except Abort as e2:
            log("restart failed:", e2)
        log("!!! Physical toolhead position is UNKNOWN. Inspect the machine before homing again.")
        return 2
    except KeyboardInterrupt:
        log("interrupted - overrides.cfg left at %g; check the machine" % read_speed())
        return 130

    write_speed(good)
    log("== done: highest passing speed %g mm/s ==" % good)
    log("final full G28 at %g mm/s (re-homes Z and ends at centre)" % good)
    if read_speed() != good:
        restart()
    gcode("G28", 180)
    cam_check(base, a.px_tol, "final")
    log("OK. Commit overrides.cfg (git add overrides.cfg; git commit) to keep %g mm/s." % good)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        log("!!!", e)
        sys.exit(2)
