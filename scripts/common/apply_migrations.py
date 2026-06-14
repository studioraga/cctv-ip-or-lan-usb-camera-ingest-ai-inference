#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.common.migrations import migrate_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply immutable SQLite migrations")
    parser.add_argument("--db-path", default="data/events/ai_camera.db")
    parser.add_argument("--migrations-dir", default="migrations")
    args = parser.parse_args()
    applied = migrate_database(args.db_path, args.migrations_dir)
    if applied:
        for name in applied:
            print(f"[APPLIED] {name}")
    else:
        print("[OK] Database is already at the latest migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
