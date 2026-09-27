import argparse
import json

import pytest

from scripts.retrain_from_corrections import run, select_records


def test_cli_provenance_selection_does_not_relabel_simulation_as_human():
    export = {"schema_version": 1, "records": [
        {"decision": "accept", "document": {"id": "simulated"}, "provenance": {"kind": "simulated_ground_truth"}},
        {"decision": "accept", "document": {"id": "unknown"}}]}
    with pytest.raises(ValueError, match="No accepted"):
        select_records(export, "client_declared_human")
    assert len(select_records(export, "all")) == 2
    assert select_records(export, "unspecified")[0]["document"]["id"] == "unknown"


def test_cli_rejects_nonexport_and_rejected_records():
    with pytest.raises(ValueError, match="schema_version"):
        select_records({}, "all")
    with pytest.raises(ValueError, match="not accepted"):
        select_records({"schema_version": 1, "records": [{"decision": "reject"}]}, "all")


def test_offline_cli_saves_exact_selected_snapshot(tmp_path, monkeypatch):
    source = tmp_path / "export.json"
    source.write_text(json.dumps({"schema_version": 1, "records": [
        {"decision": "accept", "document": {"id": "doc"}, "fields": {"total": 10},
         "provenance": {"kind": "integration_test"}}]}), encoding="utf-8")
    seen = []

    def retrain(records):
        seen.extend(records)
        return {"human_corrections_used": 0, "corrections_used": len(records)}

    monkeypatch.setattr("scripts.retrain_from_corrections.retrain_from_corrections", retrain)
    directory = tmp_path / "result"
    result = run(argparse.Namespace(api_url=None, corrections=source, provenance="integration_test", output=directory))
    assert len(seen) == 1 and result["human_corrections_used"] == 0
    assert json.loads((directory / "corrections.json").read_text())["records"] == seen
    assert json.loads((directory / "report.json").read_text())["correction_records_sha256"] == result["correction_records_sha256"]


def test_cli_does_not_send_token_over_nonlocal_plaintext_http():
    with pytest.raises(ValueError, match="HTTPS"):
        run(argparse.Namespace(api_url="http://example.test", token_env="TOKEN", provenance="all"))
