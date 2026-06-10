#!/usr/bin/env python3
import argparse
from services.common.event_db import EventDB


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default="data/events/ai_camera.db")
    args = ap.parse_args()
    db = EventDB(args.db_path)
    print(f"[INFO] event indexer DB initialized at {args.db_path}")
    print(f"[INFO] cameras={db.list_cameras()}")

if __name__ == "__main__":
    main()
