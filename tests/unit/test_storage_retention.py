import os
import time
from pathlib import Path

from services.common.storage_retention import StorageRetentionPolicy, prune_storage, storage_status


def test_storage_status_and_dry_run_prune(tmp_path: Path):
    old = tmp_path / "cap_old"
    old.mkdir()
    (old / "frame.jpg").write_bytes(b"x" * 10)
    old_ts = time.time() - 10 * 86400
    os.utime(old, (old_ts, old_ts))
    policy = StorageRetentionPolicy(root=tmp_path, retention_days=1, prune_batch=10)
    status = storage_status(policy)
    assert status["session_count"] == 1
    result = prune_storage(policy, dry_run=True)
    assert result["deleted"][0]["session_id"] == "cap_old"
    assert old.exists()
