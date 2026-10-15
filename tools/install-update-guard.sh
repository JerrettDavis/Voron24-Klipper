#!/usr/bin/env bash
# Install git post-merge hooks in the Klippain and Happy Hare checkouts (run on the printer's Pi, idempotent).
# After Moonraker/Mainsail updates either repo, the hook runs tools/mmu_v4_fix.py check. If our override of Klippain's MMU macros
# no longer matches upstream it writes ~/printer_data/config/OVERRIDE_DRIFT.txt (tools/validate.sh also reports it) and, if Klipper
# is up, prints a warning in the console. It never changes any config and never restarts anything.
#   usage: tools/install-update-guard.sh
set -u
CFG="${CFG:-$HOME/printer_data/config}"
KLIPPAIN="${KLIPPAIN:-$HOME/klippain_config}"
HH="${HH:-$HOME/Happy-Hare}"
MR="${MR:-http://localhost:7125}"

HOOK='#!/usr/bin/env bash
# installed by voron24-klipper tools/install-update-guard.sh
CFG="${CFG:-$HOME/printer_data/config}"
out=$(CFG="$CFG" python3 "$CFG/tools/mmu_v4_fix.py" check 2>&1); rc=$?
if [ $rc -ne 0 ]; then
  printf "%s  update changed upstream MMU macros that we override:\n%s\n" "$(date -Is)" "$out" > "$CFG/OVERRIDE_DRIFT.txt"
  curl -fsS -m 5 -X POST "http://localhost:7125/printer/gcode/script" --data-urlencode \
    "script=RESPOND TYPE=error MSG=\"Upstream update changed MMU macros we override: see ~/printer_data/config/OVERRIDE_DRIFT.txt, run tools/validate.sh\"" >/dev/null 2>&1
else
  rm -f "$CFG/OVERRIDE_DRIFT.txt"
fi
exit 0
'

for repo in "$KLIPPAIN" "$HH"; do
  if [ -d "$repo/.git" ]; then
    mkdir -p "$repo/.git/hooks"
    printf '%s' "$HOOK" > "$repo/.git/hooks/post-merge"
    chmod +x "$repo/.git/hooks/post-merge"
    cp "$repo/.git/hooks/post-merge" "$repo/.git/hooks/post-rewrite"
    echo "installed post-merge/post-rewrite guard in $repo"
  else
    echo "skip: $repo is not a git checkout"
  fi
done
echo "run now: python3 $CFG/tools/mmu_v4_fix.py check"
