"""Copy only the Klippain MMU macros that read the Happy Hare v3 `[mmu]` config section and rewrite them for v4.

usage: gen_mmu_fix.py KLIPPAIN_mmu.cfg OUT.cfg
"""
import re, sys

src = open(sys.argv[1], encoding="utf-8").read().replace("\r\n", "\n")
parts = re.split(r"(?m)^(?=\[gcode_macro )", src)
HEADER = """# Klippain's MMU macros (macros/hardware_functions/mmu.cfg) were written for Happy Hare v3, which had an [mmu] config section.
# Happy Hare v4 has [mmu_parameters] / [mmu_unit_parameters unit0] instead, so printer.configfile.config.mmu.* raised
# "'dict object' has no attribute 'mmu'" and aborted START_PRINT. These are copies of ONLY the affected macros with the
# lookups pointed at [mmu_unit_parameters unit0]. Included last from printer.cfg so they override the Klippain versions.
# Regenerate with tools/gen_mmu_v4_fix.py after updating Klippain (check whether upstream fixed it first).
"""
UNIT = 'printer.configfile.config["mmu_unit_parameters unit0"]'
out = [HEADER]
count = 0
for p in parts:
    if not p.startswith("[gcode_macro "):
        continue
    if "config.mmu" not in p:
        continue
    q = p
    q = re.sub(r"printer\.configfile\.config\.mmu\.sync_to_extruder\s*==\s*(\d)",
               lambda m: UNIT + ".sync_to_extruder|default(0)|int == " + m.group(1), q)
    q = q.replace("printer.configfile.config.mmu.selector_touch_enable",
                  UNIT + ".selector_touch_enable|default('n/a')")
    assert "config.mmu" not in q, "unhandled reference in: " + q[:60]
    out.append(q.rstrip() + "\n\n")
    count += 1
open(sys.argv[2], "w", encoding="utf-8", newline="\n").write("\n".join(out))
print("macros copied:", count)
