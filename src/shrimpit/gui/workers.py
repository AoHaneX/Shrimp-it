"""Run previews and sequential exports outside the GUI thread."""

import logging
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from uuid import uuid4

from PySide6.QtCore import QThread, Signal

from shrimpit.history import timestamp
from shrimpit.limits import MAX_PREVIEW_PIXELS, check_output_size
from shrimpit.processing import Options, image_info, options_for_source, process, suggested_name, thumbnail

_processing_lock = Lock()


@contextmanager
def processing_slot(worker):
    """Serialize image buffers while allowing queued jobs to be cancelled."""
    while not _processing_lock.acquire(timeout=0.05):
        if worker.isInterruptionRequested():
            yield False
            return
    try:
        yield not worker.isInterruptionRequested()
    finally:
        _processing_lock.release()


class PreviewJob(QThread):
    original_ready = Signal(int, object)
    ready = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, source: Path, options: Options, revision: int):
        super().__init__()
        self.source, self.options, self.revision = source, options, revision

    def run(self):
        try:
            with processing_slot(self) as active:
                if active:
                    self.render()
        except Exception as exc:
            logging.getLogger(__name__).exception("Preview failed")
            self.failed.emit(self.revision, str(exc))

    def render(self):
        """Render while holding the shared processing slot."""
        if self.isInterruptionRequested():
            return
        pixel_art = self.options.enlarge and self.options.upscale.mode == "pixel_art"
        before = thumbnail(self.source, pixel_art=pixel_art)
        if self.isInterruptionRequested():
            return
        self.original_ready.emit(self.revision, before)
        if self.options.enlarge:
            info = image_info(self.source)
            options = options_for_source(self.source, self.options, info.size)
            size = options.size or tuple(value * options.scale for value in info.size)
            check_output_size(size, options.output_format)
            if size[0] * size[1] > MAX_PREVIEW_PIXELS:
                self.failed.emit(
                    self.revision,
                    f"sortie prévue {size[0]} × {size[1]} ({size[0] * size[1] / 1_000_000:.1f} MP). "
                    "L’aperçu automatique est limité à 25 MP pour garder l’application réactive. "
                    "Utilisez « Agrandir et enregistrer » ; la mémoire sera vérifiée à l’export.",
                )
                return
        with TemporaryDirectory(prefix="shrimpit-preview-") as folder:
            destination = Path(folder) / suggested_name(self.source, self.options)
            result = process(self.source, destination, self.options)
            if self.isInterruptionRequested():
                return
            after = thumbnail(destination, pixel_art=pixel_art)
        self.ready.emit(self.revision, (before, after, result))


class ExportJob(QThread):
    item_done = Signal(object, object, str)
    progress = Signal(int, int)

    def __init__(self, plan, options: Options):
        super().__init__()
        self.plan, self.options = plan, options
        self.successes = 0
        self.errors = []
        self.completed = 0
        self.input_bytes = 0
        self.output_bytes = 0
        self.history_store = None
        self.history_errors = []
        self.batch_id = uuid4().hex
        self.created_at = timestamp()

    def run(self):
        for index, (source, destination) in enumerate(self.plan):
            if self.isInterruptionRequested():
                break
            try:
                with processing_slot(self) as active:
                    if not active:
                        break
                    result = process(source, destination, self.options)
                self.successes += 1
                self.input_bytes += result.input_bytes
                self.output_bytes += result.output_bytes
                if self.history_store is not None:
                    try:
                        self.history_store.record(
                            self.batch_id, self.created_at, source, result, self.options
                        )
                    except Exception as exc:
                        logging.getLogger(__name__).exception("History update failed")
                        self.history_errors.append(f"{source.name} : {exc}")
                self.item_done.emit(source, result, "")
            except Exception as exc:
                logging.getLogger(__name__).exception("Image export failed")
                message = f"{source.name} : {exc}"
                self.errors.append(message)
                self.item_done.emit(source, None, message)
            self.completed = index + 1
            self.progress.emit(self.completed, len(self.plan))
