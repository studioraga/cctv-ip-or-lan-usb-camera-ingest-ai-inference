from pathlib import Path

from services.common.model_registry import ModelRegistry, ModelRecord, sha256_file
from services.common.onnx_provider_validation import provider_report


def test_model_record_verifies_sha256(tmp_path: Path):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    digest = sha256_file(model)
    record = ModelRecord(model_id="m", role="test", path=str(model), sha256=digest, required=True)
    result = record.verify()
    assert result["ok"] is True
    assert result["sha256_matches"] is True


def test_model_registry_reports_failure_when_required_checksum_missing(tmp_path: Path):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    registry = ModelRegistry([ModelRecord(model_id="m", role="test", path=str(model), required=True)])
    result = registry.verify()
    assert result["ok"] is False
    assert result["models"][0]["status"] == "missing_checksum"


def test_provider_report_has_expected_keys():
    report = provider_report("auto")
    assert {"requested", "available", "selected", "ok", "reason"}.issubset(report)
