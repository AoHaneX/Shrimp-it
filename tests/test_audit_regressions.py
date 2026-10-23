"""Cover corrupt history and concurrent image processing failures."""

import json
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from PIL import Image

from shrimpit.gui import workers
from shrimpit.history import HistoryError, HistoryStore, timestamp
from shrimpit.processing import Options


@pytest.mark.parametrize("cancel", [False, True])
def test_export_waits_for_preview_without_blocking_cancellation(tmp_path, monkeypatch, cancel):
    started, release, exported = Event(), Event(), Event()
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    original_thumbnail, original_process = workers.thumbnail, workers.process

    def thumbnail(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return original_thumbnail(*args, **kwargs)

    def process(*args, **kwargs):
        exported.set()
        return original_process(*args, **kwargs)

    monkeypatch.setattr(workers, "thumbnail", thumbnail)
    monkeypatch.setattr(workers, "process", process)
    preview = workers.PreviewJob(source, Options(), 1)
    export = workers.ExportJob([(source, tmp_path / "output.jpg")], Options())
    preview.start()
    try:
        assert started.wait(5)
        preview.requestInterruption()
        export.start()
        assert not exported.wait(0.15)
        if cancel:
            export.requestInterruption()
            assert export.wait(2000)
            assert export.completed == 0
    finally:
        release.set()
        assert preview.wait(5000)
        assert export.wait(5000)
    assert exported.is_set() is not cancel
    assert export.successes == (0 if cancel else 1)


def test_unexpected_history_failure_does_not_mark_saved_image_as_failed(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    job = workers.ExportJob([(source, tmp_path / "output.jpg")], Options())
    job.history_store = Mock()
    job.history_store.record.side_effect = RuntimeError("Unexpected storage failure")
    job.run()
    assert job.successes == 1
    assert not job.errors
    assert len(job.history_errors) == 1
    assert (tmp_path / "output.jpg").is_file()


def test_deeply_nested_history_recovers_and_preserves_bytes(tmp_path):
    path = tmp_path / "history.json"
    contents = b"[" * 2000 + b"]" * 2000
    path.write_bytes(contents)
    assert HistoryStore(path).batches() == []
    assert next(tmp_path.glob("history-invalid-*.json")).read_bytes() == contents


def test_oversized_history_is_not_loaded_or_replaced(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    contents = b" " * 101
    path.write_bytes(contents)
    monkeypatch.setattr("shrimpit.history.MAX_HISTORY_BYTES", 100)
    with pytest.raises(HistoryError, match="volumineux"):
        HistoryStore(path).batches()
    assert path.read_bytes() == contents


@pytest.mark.parametrize("change", ["null_dimensions", "null_path"])
def test_corrupt_history_fields_cannot_break_details(tmp_path, change):
    entry = dict(
        id="image",
        created_at=timestamp(),
        operation="compression",
        source=str(Path("source.png")),
        destination="out.png",
        input_bytes=10,
        output_bytes=10,
        parameters={"input_size": [10, 10]},
    )
    if change == "null_dimensions":
        entry["parameters"]["input_size"] = None
    else:
        entry["source"] = "bad\x00.png"
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps(
            {"version": 1, "batches": [{"id": "batch", "created_at": timestamp(), "images": [entry]}]}
        ),
        encoding="utf-8",
    )
    store = HistoryStore(path)
    assert store.batches() == []
    assert store.warning
