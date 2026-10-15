#!/usr/bin/env python3
"""Two-colour Voron logo test piece: a base plate (colour 1) with the raised logo (colour 2), as ONE closed STL.

usage: python tools/make_logo_stl.py OUT.stl [--svg PATH] [--width 98] [--base 1.6] [--relief 1.2] [--png PREVIEW.png]

The colour swap is at the top of the base plate: with 0.2 mm layers and --base 1.6 add the filament change at Z = 1.8 mm
(layer 9). Needs numpy, shapely, trimesh, manifold3d, mapbox-earcut (matplotlib only for --png).
The artwork is OrcaSlicer's bundled voron_logo.svg (hexagon mark + wordmark).
"""
import argparse
import re

import numpy as np
import shapely
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union

DEFAULT_SVG = r"C:\Program Files\OrcaSlicer\resources\profiles\Voron\voron_logo.svg"


def tokens(d):
    for m in re.finditer(r"([MmLlHhVvCcSsZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)", d):
        yield m.group(1) or float(m.group(2))


def bezier(p0, p1, p2, p3, n=16):
    t = np.linspace(0, 1, n + 1)[1:, None]
    return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3).tolist()


def subpaths(d):
    """Flatten an SVG path into a list of point lists (one per subpath)."""
    toks = list(tokens(d))
    i = 0
    cmd = None
    cur = np.array([0.0, 0.0])
    start = cur.copy()
    last_c2 = None
    out, ring = [], []

    def num(k):
        nonlocal i
        v = toks[i]
        i += 1
        return v

    while i < len(toks):
        if isinstance(toks[i], str):
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                if ring:
                    out.append(ring)
                ring = []
                cur = start.copy()
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            if ring:
                out.append(ring)
            x, y = num(0), num(1)
            cur = cur + [x, y] if rel else np.array([x, y])
            start = cur.copy()
            ring = [cur.tolist()]
            cmd = "l" if rel else "L"      # implicit lineto after moveto
            last_c2 = None
        elif c == "L":
            x, y = num(0), num(1)
            cur = cur + [x, y] if rel else np.array([x, y])
            ring.append(cur.tolist())
            last_c2 = None
        elif c == "H":
            x = num(0)
            cur = np.array([cur[0] + x if rel else x, cur[1]])
            ring.append(cur.tolist())
            last_c2 = None
        elif c == "V":
            y = num(0)
            cur = np.array([cur[0], cur[1] + y if rel else y])
            ring.append(cur.tolist())
            last_c2 = None
        elif c == "C":
            v = [num(k) for k in range(6)]
            p1 = cur + v[0:2] if rel else np.array(v[0:2])
            p2 = cur + v[2:4] if rel else np.array(v[2:4])
            p3 = cur + v[4:6] if rel else np.array(v[4:6])
            ring += bezier(cur, p1, p2, p3)
            last_c2, cur = p2, p3
        elif c == "S":
            v = [num(k) for k in range(4)]
            p1 = 2 * cur - last_c2 if last_c2 is not None else cur.copy()
            p2 = cur + v[0:2] if rel else np.array(v[0:2])
            p3 = cur + v[2:4] if rel else np.array(v[2:4])
            ring += bezier(cur, p1, p2, p3)
            last_c2, cur = p2, p3
        else:
            raise ValueError("unsupported path command " + cmd)
    if ring:
        out.append(ring)
    return out


def evenodd(rings):
    poly = None
    for r in rings:
        if len(r) < 3:
            continue
        p = Polygon(r).buffer(0)
        poly = p if poly is None else poly.symmetric_difference(p)
    return poly


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--svg", default=DEFAULT_SVG)
    ap.add_argument("--width", type=float, default=98.0, help="logo width in mm")
    ap.add_argument("--base", type=float, default=1.6, help="base plate thickness mm (colour swap height)")
    ap.add_argument("--relief", type=float, default=1.2, help="raised logo height above the plate mm")
    ap.add_argument("--margin", type=float, default=4.0, help="plate margin around the logo mm")
    ap.add_argument("--png", help="write a preview image")
    a = ap.parse_args()

    svg = open(a.svg, encoding="utf-8").read()
    shapes = [evenodd(subpaths(d)) for d in re.findall(r'<path[^>]*\sd="([^"]+)"', svg)]
    logo = unary_union([s for s in shapes if s is not None and not s.is_empty])
    minx, miny, maxx, maxy = logo.bounds
    sc = a.width / (maxx - minx)
    # SVG y points down; flip, scale to mm and centre on the origin
    logo = shapely.affinity.scale(logo, xfact=sc, yfact=-sc, origin=(0, 0))
    minx, miny, maxx, maxy = logo.bounds
    logo = shapely.affinity.translate(logo, -(minx + maxx) / 2, -(miny + maxy) / 2)
    logo = logo.buffer(0.02).buffer(-0.02)            # heal hairline slivers from curve flattening
    minx, miny, maxx, maxy = logo.bounds
    plate = shapely.geometry.box(minx - a.margin, miny - a.margin, maxx + a.margin, maxy + a.margin)
    plate = plate.buffer(-3).buffer(3, join_style=1)  # 3 mm corner radius

    def extrude(poly, h, z0):
        parts = []
        for g in (poly.geoms if hasattr(poly, "geoms") else [poly]):
            if g.area < 0.02:
                continue
            m = trimesh.creation.extrude_polygon(g, h)
            m.apply_translation([0, 0, z0])
            parts.append(m)
        return trimesh.util.concatenate(parts)

    base = extrude(plate, a.base, 0.0)
    raised = extrude(logo, a.relief, a.base)
    mesh = trimesh.boolean.union([base, raised], engine="manifold")
    mesh.merge_vertices()
    mesh.apply_translation([175.0, 175.0, 0.0])        # centre on the Voron 350 bed
    assert mesh.is_watertight, "mesh is not watertight"
    mesh.export(a.out)
    ex = mesh.bounds
    print("wrote %s: %.1f x %.1f x %.1f mm, %d triangles, volume %.2f cm3, watertight=%s" % (
        a.out, ex[1][0] - ex[0][0], ex[1][1] - ex[0][1], ex[1][2] - ex[0][2], len(mesh.faces), mesh.volume / 1000, mesh.is_watertight))
    print("colour swap: add the filament change at Z = %.2f mm (top of the plate; first layer above it starts at %.1f mm)" % (a.base, a.base + 0.2))
    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 4))
        px, py = plate.exterior.xy
        ax.fill(px, py, color="#2a5d9f")
        for g in (logo.geoms if hasattr(logo, "geoms") else [logo]):
            ax.fill(*g.exterior.xy, color="#e8c11c")
            for h in g.interiors:
                ax.fill(*h.xy, color="#2a5d9f")
        ax.set_aspect("equal")
        ax.axis("off")
        fig.savefig(a.png, dpi=130, bbox_inches="tight")
        print("preview", a.png)


if __name__ == "__main__":
    main()
