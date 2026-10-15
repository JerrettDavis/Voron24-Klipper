"""Resolve OrcaSlicer system profiles (inheritance) into flat JSONs, apply overrides, write a test cube STL."""
import json, glob, os, sys, struct

ROOT = r"C:\Program Files\OrcaSlicer\resources\profiles"
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

index = {}
for f in glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    n = d.get("name")
    if isinstance(n, str) and d.get("type") in ("machine", "process", "filament"):
        # prefer Voron / OrcaFilamentLibrary copies
        if n not in index or "Voron" in f or "OrcaFilamentLibrary" in f:
            index[n] = (f, d)


def resolve(name, vendor_hint=None):
    f, d = index[name]
    parent = d.get("inherits")
    if parent:
        base = resolve(parent)
    else:
        base = {}
    merged = dict(base)
    merged.update({k: v for k, v in d.items() if k not in ("inherits",)})
    return merged


machine = resolve("Voron 2.4 350 0.4 nozzle")
process = resolve("0.20mm Standard @Voron")
filament = resolve("Generic PLA @System")

START = ("START_PRINT BED_TEMP=[bed_temperature_initial_layer_single] "
         "EXTRUDER_TEMP=[nozzle_temperature_initial_layer] CHAMBER=0 SOAK=0 "
         "MATERIAL={filament_type[initial_tool]} "
         "SIZE={first_layer_print_min[0]}_{first_layer_print_min[1]}_{first_layer_print_max[0]}_{first_layer_print_max[1]} "
         "INITIAL_TOOL={initial_tool} TOOLS_USED=!referenced_tools! TOTAL_LAYER=[total_layer_count]")

LAYER_CHANGE = ";LAYER_CHANGE\n;Z:{layer_z}\n;HEIGHT:{layer_height}\nSET_PRINT_STATS_INFO CURRENT_LAYER={layer_num + 1}"

MACHINE_NAME = "Voron 2.4 350 0.4 nozzle"      # keep the stock name so stock compatibility lists match

machine.update({
    "name": MACHINE_NAME,
    "machine_start_gcode": START,
    "machine_end_gcode": "END_PRINT",
    "change_filament_gcode": "T[next_extruder]",
    "printable_height": "300",
    "use_firmware_retraction": "1",
    "retraction_length": ["0.75"],
    "retraction_speed": ["40"],
    "deretraction_speed": ["30"],
    "z_hop": ["0.2"],
    "wipe": ["0"],
    "retract_when_changing_filament": ["0"],
    # machine time cost, $ per successful hour: 3dprint4me machineEconomics() with a $2400 basis (docs/orca-profile/README.md)
    "time_cost": "0.9",
    "enable_filament_ramming": "0",
    "cooling_tube_length": "0",
    "cooling_tube_retraction": "0",
    "parking_pos_retraction": "0",
    "extra_loading_move": "0",
    "high_current_on_filament_swap": "0",
    "machine_pause_gcode": "PAUSE",
    "layer_change_gcode": LAYER_CHANGE,
    "before_layer_change_gcode": ";BEFORE_LAYER_CHANGE\n;[layer_z]\nG92 E0",
    "time_lapse_gcode": "",
    "single_extruder_multi_material": "1",
    "machine_max_acceleration_x": ["7000", "7000"],
    "machine_max_acceleration_y": ["3500", "3500"],
    "machine_max_acceleration_extruding": ["3500", "3500"],
    "machine_max_acceleration_travel": ["8000", "8000"],
    "machine_max_speed_x": ["400", "400"],
    "machine_max_speed_y": ["400", "400"],
    "machine_max_speed_z": ["20", "20"],
    "machine_max_speed_e": ["60", "60"],
})
process.update({
    "name": "Voron24 0.20 standard",
    "default_acceleration": ["3000"],
    "outer_wall_acceleration": ["2500"],
    "inner_wall_acceleration": ["3000"],
    "initial_layer_acceleration": ["1000"],
    "travel_acceleration": ["6000"],
    "top_surface_acceleration": ["2000"],
    "prime_tower_enable": "0",
    "purge_in_prime_tower": "0",
    "enable_prime_tower": "0",
    "wipe_tower_x": "0",
    "enable_prime_tower": "0",
    "skirt_loops": "0",
    "brim_type": "no_brim",
})
filament.update({
    "name": "Generic PLA test",
    "nozzle_temperature": ["205"],
    "nozzle_temperature_initial_layer": ["210"],
    "hot_plate_temp": ["60"],
    "hot_plate_temp_initial_layer": ["60"],
    "textured_plate_temp": ["60"],
    "textured_plate_temp_initial_layer": ["60"],
    "cool_plate_temp": ["60"],
    "cool_plate_temp_initial_layer": ["60"],
    "eng_plate_temp": ["60"],
    "eng_plate_temp_initial_layer": ["60"],
    "enable_pressure_advance": ["0"],
    "filament_type": ["PLA"],
})
# leave setting_id/instantiation off so Orca treats these as user presets
for d, t in ((machine, "machine"), (process, "process"), (filament, "filament")):
    d["type"] = t
    d["from"] = "User"
    d["compatible_printers"] = [] if t == "machine" else [MACHINE_NAME]   # process/filament must name our printer
    d["compatible_printers_condition"] = ""
    d[{"machine": "printer_settings_id", "process": "print_settings_id", "filament": "filament_settings_id"}[t]] = \
        d["name"] if t != "filament" else [d["name"]]
    d.pop("compatible_prints", None)
    d["is_custom_defined"] = "1"
    for k in ("setting_id", "instantiation"):
        d.pop(k, None)
    json.dump(d, open(os.path.join(OUT, t + ".json"), "w"), indent=1)

# 25 mm cube centred at (175,175), 4 mm tall x 25 x 25 -> use 25x25x25? keep it short: 25 x 25 x 3.2
sx, sy, sz = 25.0, 25.0, 3.2
cx, cy = 175.0, 175.0
x0, x1, y0, y1, z0, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, 0.0, sz
v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
with open(os.path.join(OUT, "box.stl"), "wb") as fh:
    fh.write(b"box" + b" " * 77)
    fh.write(struct.pack("<I", len(faces)))
    for a, b, c in faces:
        fh.write(struct.pack("<3f", 0, 0, 0))
        for i in (a, b, c):
            fh.write(struct.pack("<3f", *v[i]))
        fh.write(struct.pack("<H", 0))
print("ok", OUT)
