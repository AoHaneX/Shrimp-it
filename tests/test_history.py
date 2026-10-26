"""Verify durable metadata, failure recovery, and reference-only deletion."""

import json
from threading import Event, Thread, Timer

import pytest

from shrimpit.gui.workers import ExportJob
from shrimpit.history import HistoryError, HistoryStore
from shrimpit.processing import Options


def test_persistence_grouping_sort_and_metadata(record, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    assert store.batches() == []
    first = record(store, "old", "première", "2026-10-10T12:00:00+00:00")
    record(store, "old", "seconde", "2026-10-10T12:00:00+00:00")
    record(store, "new", "troisième", "2026-10-11T12:00:00+00:00")
    batches = HistoryStore(store.path).batches()
    assert [batch["id"] for batch in batches] == ["new", "old"]
    entries = batches[1]["images"]
    assert len(entries) == 2
    assert entries[0]["id"] != entries[1]["id"]
    assert entries[0]["source"] == str(first[0].resolve())
    assert entries[0]["destination"] == str(first[1].resolve())
    assert entries[0]["input_bytes"] == first[0].stat().st_size
    assert entries[0]["parameters"]["output_format"] == "PNG"


def test_deletions_keep_images_and_remove_empty_batches(record, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    paths = [*record(store, name="one"), *record(store, name="two")]
    original = {path: path.read_bytes() for path in paths}
    entry = store.batches()[0]["images"][0]
    store.delete_entry("batch", entry["id"])
    assert len(store.batches()[0]["images"]) == 1
    store.delete_entry("batch", store.batches()[0]["images"][0]["id"])
    assert store.batches() == []
    record(store, name="one")
    record(store, batch="second", name="two")
    store.delete_batch("batch")
    assert len(store.batches()) == 1
    store.clear()
    assert HistoryStore(store.path).batches() == []
    for path, data in original.items():
        assert path.read_bytes() == data


@pytest.mark.parametrize("contents", ["{broken", "[]", '{"version":1,"batches":[{}]}', "\xff"])
def test_invalid_json_is_preserved_and_recovers(record, tmp_path, contents):
    path = tmp_path / "history.json"
    path.write_bytes(contents.encode("latin1"))
    store = HistoryStore(path)
    assert store.batches() == []
    assert "copie" in store.warning
    backup = list(tmp_path.glob("history-invalid-*.json"))
    assert len(backup) == 1
    assert backup[0].read_bytes() == contents.encode("latin1")
    record(store)
    assert len(HistoryStore(path).batches()) == 1


@pytest.mark.parametrize("created_at", ["0001-01-01T00:00:00+00:00", "9999-12-31T23:59:59+00:00"])
def test_out_of_range_dates_are_preserved_and_recover(record, tmp_path, created_at):
    store = HistoryStore(tmp_path / "history.json")
    record(store)
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["batches"][0]["images"][0]["created_at"] = created_at
    store.path.write_text(json.dumps(data), encoding="utf-8")
    assert store.batches() == []
    assert "copie" in store.warning
    assert list(tmp_path.glob("history-invalid-*.json"))


def test_second_instance_waits_for_the_lock(record, tmp_path):
    first = HistoryStore(tmp_path / "history.json")
    second = HistoryStore(first.path)
    holding, release = Event(), Event()

    def hold():
        with first._locked():
            holding.set()
            release.wait(5)

    thread = Thread(target=hold)
    thread.start()
    try:
        assert holding.wait(5)
        Timer(0.3, release.set).start()
        record(second)
    finally:
        release.set()
        thread.join(5)
    assert len(first.batches()) == 1


def test_clear_replaces_an_unreadable_history(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    path.write_bytes(b" " * 101)
    monkeypatch.setattr("shrimpit.history.MAX_HISTORY_BYTES", 100)
    store = HistoryStore(path)
    with pytest.raises(HistoryError):
        store.batches()
    store.clear()
    assert store.batches() == []


def test_atomic_write_failure_keeps_previous_history(record, tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    record(store)
    before = store.path.read_bytes()

    def fail(*args):
        raise OSError("Disk unavailable")

    monkeypatch.setattr("shrimpit.history.os.replace", fail)
    with pytest.raises(HistoryError):
        store.clear()
    assert store.path.read_bytes() == before
    assert not list(tmp_path.glob(".history-*"))


def test_multiple_store_instances_preserve_existing_batches(record, tmp_path):
    first = HistoryStore(tmp_path / "history.json")
    second = HistoryStore(first.path)
    second.batches()
    record(first, batch="first")
    record(second, batch="second", name="other")
    assert len(first.batches()) == 2


def test_worker_only_records_success_and_resolves_custom_dimensions(record, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    first, _ = record(store)
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


def test_history_failure_does_not_fail_export(record, tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    source, _ = record(store)
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


def test_cancelled_batch_keeps_completed_images(record, tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.json")
    source, _ = record(store)
    store.clear()
    job = ExportJob([(source, tmp_path / f"out{i}.png") for i in range(3)], Options(output_format="PNG"))
    job.history_store = store
    monkeypatch.setattr(job, "isInterruptionRequested", lambda: job.completed == 1)
    job.run()
    assert job.successes == 1
    assert len(store.batches()[0]["images"]) == 1


def test_missing_images_preserve_metadata(record, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    source, output = record(store)
    before = store.batches()
    source.unlink()
    output.unlink()
    assert store.batches() == before
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == 1


def test_invalid_parameter_structure_recovers_without_losing_backup(record, tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    record(store)
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["batches"][0]["images"][0]["parameters"]["upscale"] = None
    store.path.write_text(json.dumps(data), encoding="utf-8")
    assert store.batches() == []
    assert list(tmp_path.glob("history-invalid-*.json"))
