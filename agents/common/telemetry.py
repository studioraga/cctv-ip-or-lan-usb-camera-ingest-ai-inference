#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict

class JsonlLogger:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, **fields: Any) -> None:
        event: Dict[str, Any] = {
            "timestamp_ms": int(time.time() * 1000),
            "event_type": event_type,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
