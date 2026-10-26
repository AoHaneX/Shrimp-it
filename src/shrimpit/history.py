"""Store export metadata locally without copying or deleting images."""

import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from threading import RLock
from uuid import uuid4

from shrimpit.processing import options_for_source

MAX_HISTORY_BYTES = 32 * 1024 * 1024
LOCK_TIMEOUT = 2.0


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def default_history_path():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "BlueShrimp" / "Shrimpit" / "history.json"


class HistoryError(Exception):
    """Report a storage failure without interrupting image exports."""


def validate_document(data):
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("batches"), list):
        raise ValueError("Unsupported history schema")
    identifiers = set()
    for batch in data["batches"]:
        for record in [batch, *batch["images"]]:
            if not isinstance(record["id"], str) or record["id"] in identifiers:
                raise ValueError("Invalid identifier")
            identifiers.add(record["id"])
            created = datetime.fromisoformat(record["created_at"])
            if created.tzinfo is None:
                raise ValueError("Missing time zone")
            try:
                created.astimezone()
            except (OSError, OverflowError) as exc:
                # Windows cannot express dates near year 1 or 9999 in local time.
                raise ValueError("Date out of range") from exc
        if not isinstance(batch["images"], list):
            raise ValueError("Invalid image list")
        for entry in batch["images"]:
            if entry["operation"] not in ("compression", "upscale"):
                raise ValueError("Invalid operation")
            for key in ("source", "destination"):
                if not isinstance(entry[key], str) or not entry[key] or "\x00" in entry[key]:
                    raise ValueError("Invalid path")
            for key in ("input_bytes", "output_bytes"):
                if type(entry[key]) is not int or entry[key] < 0:
                    raise ValueError("Invalid file size")
            if not isinstance(entry["parameters"], dict):
                raise ValueError("Invalid parameters")
            parameters = entry["parameters"]
            settings = parameters.get("upscale", {})
            if not isinstance(settings, dict) or not isinstance(settings.get("mode", "photo"), str):
                raise ValueError("Invalid upscale settings")
            for key in ("size", "input_size", "output_size"):
                size = parameters.get(key)
                if key in parameters and key != "size" and size is None:
                    raise ValueError("Missing dimensions")
                if size is not None and (
                    not isinstance(size, list)
                    or len(size) != 2
                    or any(type(value) is not int or value <= 0 for value in size)
                ):
                    raise ValueError("Invalid dimensions")
    return data


class HistoryStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_history_path()
        self.warning = ""
        self._mutex = RLock()

    @contextmanager
    def _locked(self):
        # Lock across threads and application instances before replacing the JSON file.
        with self._mutex:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix(".lock").open("a+b") as stream:
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    acquire = partial(msvcrt.locking, stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    acquire = partial(fcntl.flock, stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Another instance may be writing: wait briefly instead of losing this update.
                deadline = time.monotonic() + LOCK_TIMEOUT
                while True:
                    try:
                        acquire()
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    stream.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _read(self):
        if not self.path.exists():
            return {"version": 1, "batches": []}
        try:
            with self.path.open("rb") as stream:
                content = stream.read(MAX_HISTORY_BYTES + 1)
            if len(content) > MAX_HISTORY_BYTES:
                raise HistoryError(
                    "Historique trop volumineux (32 Mio maximum). "
                    "Conservez une copie du fichier puis déplacez-le pour repartir avec un historique vide."
                )
            return validate_document(json.loads(content.decode("utf-8")))
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            backup = self.path.with_name(f"history-invalid-{uuid4().hex}.json")
            shutil.copy2(self.path, backup)
            self.warning = f"Historique illisible. Une copie a été conservée : {backup}"
            data = {"version": 1, "batches": []}
            self._write(data)
            return data

    def _write(self, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, prefix=".history-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def batches(self):
        try:
            with self._locked():
                data = self._read()
            return sorted(
                deepcopy(data["batches"]),
                key=lambda batch: datetime.fromisoformat(batch["created_at"]),
                reverse=True,
            )
        except OSError as exc:
            raise HistoryError(f"Impossible de lire l’historique : {exc}") from exc

    def _update(self, change):
        try:
            with self._locked():
                data = self._read()
                change(data["batches"])
                self._write(data)
        except OSError as exc:
            raise HistoryError(f"Impossible d’enregistrer l’historique : {exc}") from exc

    def record(self, batch_id, created_at, source, result, options):
        effective = options_for_source(source, options, result.input_size)
        parameters = asdict(effective)
        parameters["keep_ratio"] = options.keep_ratio
        parameters["input_size"] = list(result.input_size)
        parameters["output_size"] = list(result.output_size)
        entry = {
            "id": uuid4().hex,
            "created_at": timestamp(),
            "source": str(Path(source).resolve()),
            "destination": str(result.destination.resolve()),
            "operation": "upscale" if options.enlarge else "compression",
            "parameters": parameters,
            "input_bytes": result.input_bytes,
            "output_bytes": result.output_bytes,
        }

        def append(batches):
            batch = next((item for item in batches if item["id"] == batch_id), None)
            if batch is None:
                batch = {"id": batch_id, "created_at": created_at, "images": []}
                batches.append(batch)
            batch["images"].append(entry)

        self._update(append)

    def delete_entry(self, batch_id, entry_id):
        def remove(batches):
            for batch in batches:
                if batch["id"] == batch_id:
                    batch["images"] = [entry for entry in batch["images"] if entry["id"] != entry_id]
            batches[:] = [batch for batch in batches if batch["images"]]

        self._update(remove)

    def delete_batch(self, batch_id):
        self._update(
            lambda batches: batches.__setitem__(slice(None), [b for b in batches if b["id"] != batch_id])
        )

    def clear(self):
        # Do not read first: clearing must also work when the file cannot be loaded.
        try:
            with self._locked():
                self._write({"version": 1, "batches": []})
        except OSError as exc:
            raise HistoryError(f"Impossible d’effacer l’historique : {exc}") from exc
