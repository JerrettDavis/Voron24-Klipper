#!/usr/bin/env bash
# Read-only health check for the Voron 2.4 (Klippain + Happy Hare + ERCF) install.
# Never moves anything, never restarts anything, never writes outside /tmp.
#   usage: tools/validate.sh            (run on the printer's Pi)
# Exit status: 0 = no FAIL, 1 = at least one FAIL. WARNs never fail the run.
set -u

CFG="${CFG:-$HOME/printer_data/config}"
KLIPPAIN="${KLIPPAIN:-$HOME/klippain_config}"
HH="${HH:-$HOME/Happy-Hare}"
MR="${MR:-http://127.0.0.1:7125}"
EXPECT_MCUS="${EXPECT_MCUS:-mcu toolhead unit0}"
EXPECT_GATES="${EXPECT_GATES:-12}"

pass=0; warn=0; fail=0
ok()  { printf '  [ OK ] %s\n' "$*"; pass=$((pass+1)); }
wrn() { printf '  [WARN] %s\n' "$*"; warn=$((warn+1)); }
bad() { printf '  [FAIL] %s\n' "$*"; fail=$((fail+1)); }
hdr() { printf '\n== %s ==\n' "$*"; }

mr_get() { curl -fsS -m 10 "$MR$1" 2>/dev/null; }

# jq-free JSON helper: pyget '<json>' 'a.b.c'  (list indexes allowed, e.g. a.0.b)
pyget() {
  python3 - "$1" "$2" <<'PY' 2>/dev/null
import sys, json
d = json.loads(sys.argv[1])
for k in sys.argv[2].split("."):
    if isinstance(d, list):
        d = d[int(k)]
    elif isinstance(d, dict):
        d = d.get(k)
    else:
        d = None
    if d is None:
        break
print("" if d is None else d)
PY
}

hdr "Services"
for s in klipper moonraker crowsnest nginx; do
  if systemctl is-active --quiet "$s"; then ok "$s active"; else bad "$s NOT active"; fi
done

hdr "CAN bus"
can=$(ip -details link show can0 2>&1)
if echo "$can" | grep -q 'can0'; then
  echo "$can" | grep -q 'UP' && ok "can0 is up" || bad "can0 is down"
  echo "$can" | grep -q 'bitrate 1000000' && ok "can0 bitrate 1,000,000" || bad "can0 bitrate is not 1M (see tools/system/can0)"
  echo "$can" | grep -q 'qlen 1024' && ok "can0 txqueuelen 1024" || wrn "can0 txqueuelen is not 1024"
else
  bad "can0 interface missing (install tools/system/can0 into /etc/network/interfaces.d/)"
fi

hdr "Klipper / MCUs"
info=$(mr_get /printer/info) || info=""
if [ -z "$info" ]; then
  bad "Moonraker not answering on $MR"
else
  state=$(pyget "$info" result.state)
  if [ "$state" = ready ]; then ok "Klipper state: ready"; else bad "Klipper state: $state - $(pyget "$info" result.state_message | head -c 200)"; fi
  host_ver=$(pyget "$info" result.software_version)
  echo "         host version: $host_ver"
  q="mcu"
  for m in $EXPECT_MCUS; do [ "$m" != mcu ] && q="$q&mcu%20$m"; done
  mcus=$(mr_get "/printer/objects/query?$q") || mcus=""
  for m in $EXPECT_MCUS; do
    key="mcu"; [ "$m" != mcu ] && key="mcu $m"
    v=$(python3 - "$mcus" "$key" <<'PY' 2>/dev/null
import sys, json
r = json.loads(sys.argv[1])["result"]["status"]
print(r.get(sys.argv[2], {}).get("mcu_version", ""))
PY
)
    if [ -z "$v" ]; then
      bad "MCU '$m' not reporting"
    elif [ "${v%-dirty}" = "${host_ver%-dirty}" ]; then
      ok "MCU '$m' firmware $v matches host"
    else
      wrn "MCU '$m' firmware $v differs from host $host_ver (README > Firmware)"
    fi
  done
fi

hdr "Happy Hare"
mmu=$(mr_get "/printer/objects/query?mmu&mmu_machine") || mmu=""
if [ -z "$mmu" ]; then
  bad "MMU objects not found (Happy Hare not loaded?)"
else
  [ "$(pyget "$mmu" result.status.mmu.enabled)" = True ] && ok "MMU enabled" || bad "MMU not enabled"
  g=$(pyget "$mmu" result.status.mmu.num_gates)
  [ "$g" = "$EXPECT_GATES" ] && ok "$g gates configured" || bad "num_gates=$g (expected $EXPECT_GATES)"
  echo "         happy_hare_version: $(pyget "$mmu" result.status.mmu_machine.happy_hare_version)  homed: $(pyget "$mmu" result.status.mmu.is_homed)  action: $(pyget "$mmu" result.status.mmu.action)"
fi
if [ -d "$HH/.git" ]; then echo "         Happy-Hare checkout: $(git -C "$HH" describe --tags --always 2>/dev/null)"; else bad "$HH is not a git checkout"; fi

hdr "Config tree"
for l in config macros moonraker scripts; do
  if [ -L "$CFG/$l" ] && [ -e "$CFG/$l" ]; then ok "symlink $l -> $(readlink "$CFG/$l")"; else bad "symlink $CFG/$l missing or broken (run tools/restore.sh links)"; fi
done
for f in printer.cfg mcu.cfg overrides.cfg variables.cfg moonraker.conf crowsnest.conf save_variables.cfg mmu/.mmu_config mmu/base/mmu_hardware_unit0.cfg mmu/base/mmu_parameters_unit0.cfg; do
  [ -f "$CFG/$f" ] && ok "$f present" || bad "$f missing"
done
if git -C "$CFG" rev-parse >/dev/null 2>&1; then
  dirty=$(git -C "$CFG" status --porcelain | wc -l)
  if [ "$dirty" = 0 ]; then ok "printer config repo clean"; else wrn "printer config repo has $dirty uncommitted change(s) (expected after calibration: tools/backup-calibration.sh)"; fi
fi
if [ -d "$KLIPPAIN/.git" ]; then
  d=$(git -C "$KLIPPAIN" status --porcelain | wc -l)
  if [ "$d" = 0 ]; then ok "Klippain checkout is unmodified"; else bad "Klippain checkout has $d local modification(s); move them into mcu.cfg/overrides.cfg"; fi
else
  bad "$KLIPPAIN missing"
fi
if grep -q 'filename: *~/printer_data/config/save_variables.cfg' "$CFG/variables.cfg" 2>/dev/null; then
  ok "live Happy Hare store is save_variables.cfg (mmu/mmu_vars.cfg is unused)"
else
  wrn "could not confirm which [save_variables] file is live"
fi

hdr "Webcam"
cams=$(mr_get /server/webcams/list) || cams=""
n=$(python3 - "$cams" <<'PY' 2>/dev/null
import sys, json
print(len(json.loads(sys.argv[1])["result"]["webcams"]))
PY
)
if [ "${n:-0}" -ge 1 ]; then ok "Moonraker has $n webcam(s) registered"; else bad "no webcam registered in Moonraker ([webcam printer] in moonraker.conf)"; fi
tmp=$(mktemp)
code=$(curl -s -m 10 -o "$tmp" -w '%{http_code} %{content_type}' "http://127.0.0.1/webcam/?action=snapshot")
case "$code" in
  "200 image/jpeg"*) ok "snapshot via nginx: $code, $(wc -c <"$tmp") bytes, $(file -b "$tmp" | grep -oE '[0-9]+x[0-9]+' | tail -1)" ;;
  *) bad "snapshot via nginx failed: $code" ;;
esac
rm -f "$tmp"
dev=$(sed -n 's/^device:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "$CFG/crowsnest.conf" | head -1)
if [ -n "$dev" ] && [ -e "$dev" ]; then ok "camera device $dev exists"; else bad "camera device '$dev' not found"; fi

hdr "Summary"
printf '  %d ok, %d warn, %d fail\n' "$pass" "$warn" "$fail"
[ "$fail" = 0 ]
