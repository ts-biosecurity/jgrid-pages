"""Build-only public Basemaps config. Confirm referer restrictions before use."""
import json
import os
from pathlib import Path
import sys

key = os.environ.get("CARTO_BASEMAPS_KEY", "").strip()
if not key:
    raise SystemExit("CARTO_BASEMAPS_KEY missing; refusing deployment")
destination = Path(sys.argv[1])
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps({"basemapsKey": key}) + "\n", encoding="utf-8")
