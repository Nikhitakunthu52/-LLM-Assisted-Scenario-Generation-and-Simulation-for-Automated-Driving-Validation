#!/bin/bash
# Double-click in Finder to pick a crash scenario and play it in esmini (daylight view).
cd "$(dirname "$0")/.." || exit 1
ESMINI="tools/esmini-demo/bin/esmini"
MODELS="tools/esmini-demo/resources/models"
if [ ! -x "$ESMINI" ]; then
  echo "esmini not found - run ./scripts/setup_esmini.sh first"; read -r -p "Press Enter to close"; exit 1
fi
names=("CIREN_8392  Head-on, REAL case (lane departure at night)"
       "CISS_A1     Rear-end, distracted driver"
       "CISS_A2     Left turn across path at city intersection"
       "SGO_B1      Rear-end into stopped automated vehicle"
       "SGO_B2      Left turn vs automated vehicle (ADS avoids crash)")
files=(CIREN_8392 CISS_A1 CISS_A2 SGO_B1 SGO_B2)
while true; do
  echo ""
  echo "=== crash2sim scenarios in esmini ==="
  for i in "${!names[@]}"; do echo "  $((i+1))) ${names[$i]}"; done
  echo "  q) quit"
  echo "Controls in esmini: Space pause | drag/scroll camera | k camera mode | Tab switch car | Esc close"
  read -r -p "Pick 1-5: " c
  [[ "$c" == "q" ]] && exit 0
  if [[ "$c" =~ ^[1-5]$ ]]; then
    f="scenarios/demo/${files[$((c-1))]}.xosc"
    "$ESMINI" --window 60 60 1280 720 --path "$MODELS" --osc "$f" --hide_route_waypoints --info_text 1
  fi
done
