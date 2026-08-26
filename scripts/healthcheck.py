#!/usr/bin/env python3
"""Exit non-zero when the offline pilot health check fails."""
from __future__ import annotations
import json
from app.health import check_health

status = check_health()
print(json.dumps(status.to_dict(), ensure_ascii=False))
raise SystemExit(0 if status.healthy else 1)
