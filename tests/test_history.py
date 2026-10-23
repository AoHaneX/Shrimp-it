"""Verify durable metadata, failure recovery, and reference-only deletion."""

import json

import pytest
from PIL import Image

from shrimpit.engine import ConversionResult
from shrimpit.gui.workers import ExportJob
from shrimpit.history import HistoryError, HistoryStore, timestamp
from shrimpit.processing import Options


def record(store, tmp_path, batch="batch", name="photo", created_at=None):
    source = tmp_path / f"{name}.png"
    output = tmp_path / f"{name}-min.png"
    Image.new("RGBA", (12, 8), (80, 120, 220, 90)).save(source)
    Image.new("RGBA", (12, 8), (80, 120, 220, 90)).save(output)
    result = ConversionResult(output, source.stat().st_size, output.stat().st_size, (12, 8), (12, 8))
    store.record(batch, created_at or timestamp(), source, result, Options(output_format="PNG"))
    return source, output


def test_persistence_grouping_sort_and_metadata(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    assert store.batches() == []
    first = record(store, tmp_path, "old", "première", "2026-10-10T12:00:00+00:00")
    record(store, tmp_path, "old", "seconde", "2026-10-10T12:00:00+00:00")
    record(store, tmp_path, "new", "troisième", "2026-10-11T12:00:00+00:00")
    batches = HistoryStore(store.path).batches()
    assert [batch["id"] for batch in batches] == ["new", "old"]
    entries = batches[1]["images"]
    assert len(entries) == 2
    assert entries[0]["id"] != entries[1]["id"]
    assert entries[0]["source"] == str(first[0].resolve())
    assert entries[0]["destination"] == str(first[1].resolve())
    assert entries[0]["input_bytes"] == first[0].stat().st_size
    assert entries[0]["parameters"]["output_format"] == "PNG"


def test_deletions_keep_images_and_remove_empty_batches(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    paths = [*record(store, tmp_path, name="one"), *record(store, tmp_path, name="two")]
    original = {path: path.read_bytes() for path in paths}
    entry = store.batches()[0]["images"][0]
    store.delete_entry("batch", entry["id"])
    assert len(store.batches()[0]["images"]) == 1
    store.delete_entry("batch", store.batches()[0]["images"][0]["id"])
    assert store.batches() == []
    record(store, tmp_path, name="one")
    record(store, tmp_path, batch="second", name="two")
    store.delete_batch("batch")
    assert len(store.batches()) == 1
    store.clear()
    assert HistoryStore(store.path).batches() == []
    for path, data in original.items():
        assert path.read_bytes() == data


@pytest.mark.parametrize("contents", ["{broken", "[]", '{"version":1,"batches":[{}]}', "\xff"])
def test_invalid_json_is_preserved_and_recovers(tmp_path, contents):
    path = tmp_path / "history.json"
    path.write_bytes(contents.encode("latin1"))
    store = HistoryStore(path)
    assert store.batches() == []
    assert "copie" in store.warning
    backup = list(tmp_path.glob("history-invalid-*.json"))
    assert len(backup) == 1
    assert backup[0].read_bytes() == contents.encode("latin1")
    record(store, tmp_path)
    assert len(HistoryStore(path).batches()) == 1


def test_atomic_write_failure_keeps_previous_history(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    record(store, tmp_path)
    before = store.path.read_bytes()

    def fail(*args):
        raise OSError("Disk unavailable")

    monkeypatch.setattr("shrimpit.history.os.replace", fail)
    with pytest.raises(HistoryError):
        store.clear()
    assert store.path.read_bytes() == before
    assert not list(tmp_path.glob(".history-*"))


def test_multiple_store_instances_preserve_existing_batches(tmp_path):
    first = HistoryStore(tmp_path / "history.json")
    second = HistoryStore(first.path)
    second.batches()
    record(first, tmp_path, batch="first")
    record(second, tmp_path, batch="second", name="other")
    assert len(first.batches()) == 2


def test_worker_only_records_success_and_resolves_custom_dimensions(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    first, _ = record(store, tmp_path)
    store.clear()
    options = Options(enlarge=True, output_format="PNG", size=(24, 24), keep_ratio=True)
    job = ExportJob([(first, tmp_path / "up.png"), (tmp_path / "absent.png", tmp_path / "fail.png")], options)
    job.history_store = store
    job.run()
    assert job.successes == 1
    assert len(job.errors) == 1
    assert not job.history_errors
    batch = store.batches()[0]
    assert batch["id"] == job.batch_id
    assert len(batch["images"]) == 1
    entry = batch["images"][0]
    assert entry["operation"] == "upscale"
    assert entry["parameters"]["size"] == [24, 16]
    assert entry["parameters"]["output_size"] == [24, 16]


def test_history_failure_does_not_fail_export(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    source, _ = record(store, tmp_path)
    job = ExportJob([(source, tmp_path / "converted.jpg")], Options())
    job.history_store = store

    def fail(*args):
        raise HistoryError("History unavailable")

    monkeypatch.setattr(store, "record", fail)
    job.run()
    assert job.successes == 1
    assert not job.errors
    assert len(job.history_errors) == 1
    assert (tmp_path / "converted.jpg").is_file()


def test_cancelled_batch_keeps_completed_images(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    source, _ = record(store, tmp_path)
    store.clear()
    job = ExportJob([(source, tmp_path / f"out{i}.png") for i in range(3)], Options(output_format="PNG"))
    job.history_store = store
    monkeypatch.setattr(job, "isInterruptionRequested", lambda: job.completed == 1)
    job.run()
    assert job.successes == 1
    assert len(store.batches()[0]["images"]) == 1


def test_missing_images_preserve_metadata(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    source, output = record(store, tmp_path)
    before = store.batches()
    source.unlink()
    output.unlink()
    assert store.batches() == before
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == 1


def test_invalid_parameter_structure_recovers_without_losing_backup(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    record(store, tmp_path)
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["batches"][0]["images"][0]["parameters"]["upscale"] = None
    store.path.write_text(json.dumps(data), encoding="utf-8")
    assert store.batches() == []
    assert list(tmp_path.glob("history-invalid-*.json"))
