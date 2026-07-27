#!/usr/bin/env bash
# Démarre le Symp's Kiosk. Aucune dépendance à installer : Python 3 suffit.
set -euo pipefail

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1 && python -c 'import sys; sys.exit(sys.version_info[0] < 3)'; then
  PY=python
else
  echo
  echo "  Python 3 est introuvable sur cette machine."
  echo "  Sur macOS, lancez « xcode-select --install » dans le Terminal,"
  echo "  ou installez Python depuis https://www.python.org/downloads/"
  echo
  exit 1
fi

exec "$PY" symps.py "$@"
