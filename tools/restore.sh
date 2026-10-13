#!/usr/bin/env bash
# Rebuild / repair the printer's software layout from this repo. Idempotent; safe to re-run.
# Does NOT move the printer, flash firmware, run calibration, or run Happy Hare's interactive installer.
#
#   usage: tools/restore.sh [--dry-run] <step...>
#   steps: links      recreate the Klippain symlinks (config macros moonraker scripts) in printer_data/config
#          klippain   clone ~/klippain_config if missing and check out the commit pinned in .VERSION
#          happyhare  clone ~/Happy-Hare if missing and re-link its Klipper/Moonraker extras (install.sh -f)
#          can0       install tools/system/can0 into /etc/network/interfaces.d (needs sudo)
#          services   restart crowsnest + moonraker, and Klipper ONLY if the printer is idle
#          all        klippain happyhare links can0 services (in that order)
#
# Typical disaster recovery on a fresh Pi (after Klipper, Moonraker, Mainsail, Crowsnest via KIAUH):
#   git clone https://github.com/JerrettDavis/voron24-klipper ~/printer_data/config   (move the old dir aside first)
#   ~/printer_data/config/tools/restore.sh all
#   ~/printer_data/config/tools/validate.sh
set -eu

CFG="${CFG:-$HOME/printer_data/config}"
KLIPPAIN="${KLIPPAIN:-$HOME/klippain_config}"
HH="${HH:-$HOME/Happy-Hare}"
KLIPPAIN_URL="${KLIPPAIN_URL:-https://github.com/Frix-x/klippain.git}"
HH_URL="${HH_URL:-https://github.com/moggieuk/Happy-Hare.git}"
MR="${MR:-http://127.0.0.1:7125}"
dry=0

run() { if [ "$dry" = 1 ]; then echo "DRY: $*"; else echo "+ $*"; "$@"; fi; }
say() { printf '\n== %s ==\n' "$*"; }

step_klippain() {
  say "Klippain checkout"
  if [ ! -d "$KLIPPAIN/.git" ]; then run git clone "$KLIPPAIN_URL" "$KLIPPAIN"; fi
  want=$(tr -d '[:space:]' < "$CFG/.VERSION" 2>/dev/null || true)
  if [ -n "$want" ] && [ -d "$KLIPPAIN/.git" ]; then
    if [ -n "$(git -C "$KLIPPAIN" status --porcelain)" ]; then
      echo "Klippain checkout has local modifications; refusing to move it. Inspect: git -C $KLIPPAIN diff"
      echo "(The MMB board_pins fix lives in mcu.cfg now; plain 'git -C $KLIPPAIN checkout -- .' is correct.)"
      return 1
    fi
    echo ".VERSION pins Klippain at ${want:0:8}; currently at $(git -C "$KLIPPAIN" rev-parse --short=8 HEAD)"
    echo "Only checking out the pinned commit if it differs and exists locally; otherwise leaving HEAD (Klippain is updated via Moonraker)."
    if [ "$(git -C "$KLIPPAIN" rev-parse HEAD)" != "$want" ] && git -C "$KLIPPAIN" cat-file -e "$want^{commit}" 2>/dev/null; then
      run git -C "$KLIPPAIN" checkout --detach "$want"
    fi
  fi
}

step_happyhare() {
  say "Happy Hare"
  if [ ! -d "$HH/.git" ]; then run git clone "$HH_URL" "$HH"; fi
  # -f = "just restore klipper/moonraker symlinks". We deliberately do NOT run ./install.sh (or -i):
  # it re-renders mmu/base/*.cfg from mmu/.mmu_config and would overwrite our reviewed hardware settings.
  if [ "$dry" = 1 ]; then echo "DRY: (cd $HH && ./install.sh -f)"; else (cd "$HH" && ./install.sh -f); fi
}

step_links() {
  say "Klippain symlinks"
  for l in config macros moonraker scripts; do
    if [ -d "$KLIPPAIN/$l" ]; then run ln -sfn "$KLIPPAIN/$l" "$CFG/$l"; else echo "missing $KLIPPAIN/$l"; return 1; fi
  done
}

step_can0() {
  say "can0 interface"
  src="$CFG/tools/system/can0"
  if cmp -s "$src" /etc/network/interfaces.d/can0 2>/dev/null; then echo "already installed"; return 0; fi
  run sudo cp "$src" /etc/network/interfaces.d/can0
  echo "Bring it up with: sudo ifup can0   (or reboot)"
}

step_services() {
  say "Services"
  state=$(curl -fsS -m 5 "$MR/printer/objects/query?print_stats" 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["status"]["print_stats"]["state"])' 2>/dev/null || echo unknown)
  run curl -fsS -m 20 -X POST "$MR/machine/services/restart?service=crowsnest" >/dev/null
  run curl -fsS -m 20 -X POST "$MR/machine/services/restart?service=moonraker" >/dev/null || true
  case "$state" in
    standby|complete|cancelled|error|unknown)
      sleep 5; run curl -fsS -m 20 -X POST "$MR/printer/restart" >/dev/null || sudo systemctl restart klipper ;;
    *) echo "print_stats.state=$state: NOT restarting Klipper while printing/paused." ;;
  esac
}

[ "${1:-}" = "--dry-run" ] && { dry=1; shift; }
[ $# -ge 1 ] || { sed -n '2,15p' "$0"; exit 2; }
for s in "$@"; do
  case "$s" in
    klippain)  step_klippain ;;
    happyhare) step_happyhare ;;
    links)     step_links ;;
    can0)      step_can0 ;;
    services)  step_services ;;
    all)       step_klippain; step_happyhare; step_links; step_can0; step_services ;;
    *) echo "unknown step: $s"; exit 2 ;;
  esac
done
echo; echo "Done. Next: tools/validate.sh"
