"""Image selection, processing controls, and previews."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QBoxLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from shrimpit.engine import EXTENSIONS
from shrimpit.errors import ConversionError
from shrimpit.examples import example_preview
from shrimpit.filenames import validate_filename
from shrimpit.gui.comparison import ComparisonPreview
from shrimpit.gui.output_settings import OutputSettings
from shrimpit.gui.pages.common import page_heading
from shrimpit.gui.theme import icon
from shrimpit.gui.widgets import DropZone, PreviewCard, label, panel
from shrimpit.gui.workers import ExportJob, PreviewJob
from shrimpit.processing import export_plan, image_info, readable_size, suggested_name


class ProcessingPage(QWidget):
    busy_changed = Signal(bool)

    def __init__(self, enlarge=False, settings=None):
        super().__init__()
        self.setObjectName("page")
        self.enlarge = enlarge
        self.settings = settings
        self.shutting_down = False
        self.sources = []
        self.infos = {}
        self.job = None
        self.preview_job = None
        self.revision = 0
        self.preview_payload = None
        # Only the content scrolls: the export bar stays visible at every window size.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 24, 22, 14)
        layout.setSpacing(14)
        page_heading(
            layout,
            "Agrandissement" if enlarge else "Compression",
            "Agrandissez vos images localement, sans IA."
            if enlarge
            else "Réduisez la taille de vos images en ajustant leur qualité.",
            "expand" if enlarge else "image",
        )
        self.drop_zone = DropZone(multiple=True)
        self.drop_zone.files_dropped.connect(self.add_files)
        self.drop_zone.choose_clicked.connect(self.choose_files)
        layout.addWidget(self.drop_zone)
        self.import_errors = label("", "warning")
        self.import_errors.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.import_errors.hide()
        layout.addWidget(self.import_errors)

        self.body = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.body.setSpacing(14)
        preview_panel, preview_layout = panel()
        preview_header = QHBoxLayout()
        preview_header.addWidget(label("Aperçu avant / après", "section"), 1)
        self.preview_toggle = QPushButton("Côte à côte")
        self.preview_toggle.setToolTip("Changer le mode de comparaison des aperçus")
        self.preview_toggle.setCheckable(True)
        self.preview_toggle.toggled.connect(self.toggle_preview)
        preview_header.addWidget(self.preview_toggle)
        preview_layout.addLayout(preview_header)
        self.preview_stack = QStackedWidget()
        self.comparison = ComparisonPreview()
        self.preview_stack.addWidget(self.comparison)
        classic = QWidget()
        preview_row = QHBoxLayout(classic)
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.setSpacing(10)
        self.before = PreviewCard("Avant")
        self.after = PreviewCard("Après · aperçu calculé")
        preview_row.addWidget(self.before)
        preview_row.addWidget(self.after)
        self.preview_stack.addWidget(classic)
        preview_layout.addWidget(self.preview_stack, 1)
        self.preview_status = label("Importez une image pour afficher un aperçu.", "muted")
        preview_layout.addWidget(self.preview_status)
        self.body.addWidget(preview_panel, 3)

        self.settings_panel, controls = panel()
        controls.addWidget(label("01   Vos images", "section"))
        self.files = QListWidget()
        self.files.setAccessibleName("Images importées")
        # Show about five rows so a batch can be reviewed without a tiny scroll area.
        self.files.setMaximumHeight(150)
        self.files.setMinimumHeight(64)
        self.files.currentRowChanged.connect(self.selection_changed)
        controls.addWidget(self.files)
        file_actions = QHBoxLayout()
        self.info = label("Aucune image sélectionnée", "muted")
        file_actions.addWidget(self.info, 1)
        self.remove = QPushButton()
        self.remove.setObjectName("removeImages")
        self.remove.setIcon(icon("close", "#ffffff"))
        self.remove.setToolTip("Retirer l’image sélectionnée")
        self.remove.setAccessibleName("Retirer l’image sélectionnée")
        self.remove.setFixedSize(34, 34)
        self.remove.clicked.connect(self.remove_selected)
        file_actions.addWidget(self.remove)
        self.clear = QPushButton("Tout retirer")
        self.clear.setObjectName("removeImages")
        self.clear.clicked.connect(self.clear_images)
        file_actions.addWidget(self.clear)
        controls.addLayout(file_actions)
        self.output = OutputSettings(enlarge, settings)
        controls.addWidget(self.output)
        self.body.addWidget(self.settings_panel, 2)
        layout.addLayout(self.body)
        layout.addStretch()

        action_bar = QFrame()
        action_bar.setObjectName("actionBar")
        actions = QHBoxLayout(action_bar)
        actions.setContentsMargins(22, 12, 22, 14)
        actions.setSpacing(14)
        self.status = label(
            "Prêt à agrandir votre image." if enlarge else "Prêt à compresser vos images.", "status"
        )
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        actions.addWidget(self.status, 1)
        self.export = QPushButton("Agrandir et enregistrer…" if enlarge else "Compresser et enregistrer…")
        self.export.setObjectName("action")
        self.export.setMinimumWidth(260)
        self.export.clicked.connect(self.start_export)
        self.export.setEnabled(False)
        actions.addWidget(self.export, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(action_bar)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(350)
        self.preview_timer.timeout.connect(self.start_preview)
        self.output.changed.connect(self.settings_changed)
        self.settings_changed()

    @property
    def source(self):
        row = self.files.currentRow()
        return self.sources[row] if 0 <= row < len(self.sources) else None

    def options(self):
        return self.output.options()

    @Slot()
    def settings_changed(self):
        for canvas in (self.before.canvas, self.after.canvas, self.comparison.canvas):
            canvas.pixel_art = self.output.pixel_mode
            canvas.update()
        self.schedule_preview()

    @Slot()
    def choose_files(self):
        folder = str(self.settings.value("input_folder", "")) if self.settings else ""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des images", folder, "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if paths and self.settings:
            self.settings.setValue("input_folder", str(Path(paths[0]).parent))
        self.add_files([Path(p) for p in paths])

    @Slot(list)
    def add_files(self, paths):
        if self.job:
            return
        accepted, errors = [], []
        for path in paths:
            path = Path(path)
            try:
                path = path.resolve()
                info = image_info(path)
                accepted.append((path, info))
            except Exception as exc:
                errors.append(f"{path.name} : {exc}")
        for path, info in accepted:
            if path not in self.sources:
                self.sources.append(path)
                self.infos[path] = info
                self.files.addItem(path.name)
                self.files.item(self.files.count() - 1).setToolTip(str(path))
        if accepted:
            self.files.setCurrentRow(self.sources.index(accepted[-1][0]))
        self.export.setEnabled(bool(self.sources))
        self.show_import_errors(errors)
        self.status.setText(f"{len(self.sources)} image(s) prête(s).")

    def show_import_errors(self, errors):
        """Explain refused files next to the drop zone, where the user just acted."""
        self.import_errors.setText("Fichiers non importés :\n" + "\n".join(errors) if errors else "")
        self.import_errors.setVisible(bool(errors))

    @Slot(int)
    def selection_changed(self, row):
        self.before.clear()
        self.after.clear()
        self.preview_payload = None
        if self.source:
            self.before.heading.setText("Avant")
            self.after.heading.setText("Après · aperçu calculé")
            info = self.infos[self.source]
            self.info.setText(
                f"{info.size[0]} × {info.size[1]} · {readable_size(info.byte_count)} · {info.format}"
            )
            self.output.set_source(self.source, info.size)
        else:
            self.info.setText("Aucune image sélectionnée")
            self.output.set_source(None, None)
        self.schedule_preview()

    @Slot()
    def remove_selected(self):
        row = self.files.currentRow()
        if row < 0 or self.job:
            return
        source = self.sources.pop(row)
        self.infos.pop(source, None)
        self.files.blockSignals(True)
        self.files.takeItem(row)
        self.files.setCurrentRow(min(row, len(self.sources) - 1))
        self.files.blockSignals(False)
        self.selection_changed(self.files.currentRow())
        self.export.setEnabled(bool(self.sources))

    def output_name(self, source, options=None):
        return self.output.output_name(source, self.infos[source].size, options)

    def proposed_name(self, source, options=None):
        return suggested_name(source, options or self.options(), self.infos[source].size)

    def clear_images(self):
        if self.job:
            return
        self.sources.clear()
        self.infos.clear()
        self.files.clear()
        self.show_import_errors([])
        self.selection_changed(-1)
        self.export.setEnabled(False)
        self.status.setText("Liste vidée. Vos fichiers originaux sont conservés.")

    def schedule_preview(self):
        if self.shutting_down:
            return
        self.revision += 1
        self.after.clear()
        self.preview_payload = None
        if self.source:
            self.comparison.canvas.message = "Calcul de l’aperçu…"
            self.sync_comparison()
            self.preview_status.setText("Calcul de l’aperçu…")
            self.preview_timer.start()
        else:
            self.preview_timer.stop()
            self.show_examples()

    def toggle_preview(self, classic):
        self.preview_stack.setCurrentIndex(1 if classic else 0)
        self.preview_toggle.setText("Curseur avant/après" if classic else "Côte à côte")

    def sync_comparison(self):
        self.comparison.display(
            self.before.canvas.pixmap,
            self.after.canvas.pixmap,
            self.before.image_size,
            self.after.image_size,
            self.before.details.text(),
            self.after.details.text(),
        )

    def show_examples(self):
        try:
            before, after, original, result = example_preview(self.enlarge)
            self.before.display(before, original.size, readable_size(original.byte_count))
            self.after.display(after, result.size, readable_size(result.byte_count))
            self.before.heading.setText("Avant · exemple")
            self.after.heading.setText("Après · exemple")
            preset = "×2, Lanczos et netteté légère" if self.enlarge else "JPEG, qualité 80"
            self.preview_status.setText(
                f"Exemple de démonstration ({preset}). Glissez la séparation ou importez vos images."
            )
        except (OSError, ValueError, ConversionError):
            self.before.clear()
            self.after.clear()
            self.comparison.canvas.message = "Importez une image pour afficher un aperçu."
            self.preview_status.setText("Exemple indisponible. Vous pouvez importer vos images.")
        self.sync_comparison()

    @Slot()
    def start_preview(self):
        if self.shutting_down or self.preview_job or self.job or not self.source:
            return
        self.preview_job = PreviewJob(self.source, self.options(), self.revision)
        self.preview_job.original_ready.connect(self.preview_original)
        self.preview_job.ready.connect(self.preview_ready)
        self.preview_job.failed.connect(self.preview_failed)
        self.preview_job.finished.connect(self.preview_finished)
        self.preview_job.start()

    @Slot(int, object)
    def preview_original(self, revision, data):
        if revision == self.revision and self.source:
            info = self.infos[self.source]
            self.before.display(data, info.size, readable_size(info.byte_count))
            self.sync_comparison()

    @Slot(int, object)
    def preview_ready(self, revision, payload):
        if revision != self.revision:
            return
        before, after, result = payload
        self.preview_payload = payload
        self.before.display(before, result.input_size, readable_size(result.input_bytes))
        self.after.display(after, result.output_size, readable_size(result.output_bytes))
        self.sync_comparison()
        difference = result.input_bytes - result.output_bytes
        change = (
            f"Gain : {readable_size(difference)}"
            if difference >= 0
            else f"Plus volumineux de {readable_size(-difference)}"
        )
        self.preview_status.setText(f"{change} · Aperçu calculé, aucun fichier enregistré.")

    @Slot(int, str)
    def preview_failed(self, revision, message):
        if revision == self.revision:
            self.comparison.canvas.message = "Aperçu indisponible"
            self.comparison.canvas.update()
            self.preview_status.setText(f"Aperçu indisponible : {message}")

    @Slot()
    def preview_finished(self):
        previous = self.preview_job.revision
        self.preview_job.deleteLater()
        self.preview_job = None
        if not self.shutting_down and previous != self.revision and self.source and not self.job:
            self.preview_timer.start()

    @Slot()
    def start_export(self):
        if self.job or not self.sources:
            return
        self.output.store_name()
        options = self.options()
        try:
            if len(self.sources) == 1:
                source = self.sources[0]
                name = self.output_name(source, options)
                # Like a batch: reuse the last output folder and propose a free numbered name.
                folder = Path(self.output_folder(source.parent))
                if not folder.is_dir():
                    folder = source.parent
                suggestion = export_plan([source], folder, {source: name}, options)[0][1]
                extensions = sorted(EXTENSIONS[options.output_format])
                filename, _ = QFileDialog.getSaveFileName(
                    self,
                    "Enregistrer l’image",
                    str(suggestion),
                    f"{self.output.format.currentText()} ({' '.join('*' + e for e in extensions)})",
                    options=QFileDialog.Option.DontConfirmOverwrite,
                )
                if not filename:
                    return
                destination = Path(filename)
                if not destination.suffix:
                    destination = destination.with_suffix(Path(self.proposed_name(source, options)).suffix)
                validate_filename(destination.name)
                # Refuse before switching screens: the engine never overwrites a file.
                if destination.suffix.lower() not in extensions:
                    raise ConversionError(
                        f"l’extension {destination.suffix} ne correspond pas au format "
                        f"{self.output.format.currentText()}. Utilisez {' ou '.join(extensions)}."
                    )
                if destination.exists():
                    raise ConversionError(
                        f"{destination.name} existe déjà. Les fichiers existants ne sont jamais "
                        "remplacés : choisissez un autre nom."
                    )
                plan = [(source, destination)]
            else:
                initial = self.output_folder(self.sources[0].parent)
                folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier de sortie", initial)
                if not folder:
                    return
                names = {source: self.output_name(source, options) for source in self.sources}
                plan = export_plan(self.sources, Path(folder), names, options)
        except Exception as exc:
            self.status.setText(f"Échec : {exc}")
            return
        if self.settings:
            self.settings.setValue("output_folder", str(plan[0][1].parent))
        self.preview_timer.stop()
        if self.preview_job:
            self.preview_job.requestInterruption()
        self.job = ExportJob(plan, options)
        self.job.item_done.connect(self.item_done)
        self.job.finished.connect(self.export_finished)
        self.drop_zone.setEnabled(False)
        self.settings_panel.setEnabled(False)
        self.export.setEnabled(False)
        self.status.setText("Traitement en cours…")
        self.busy_changed.emit(True)
        self.job.start()

    def output_folder(self, default):
        """Return the folder of the previous export, or the given default."""
        return str(self.settings.value("output_folder", str(default))) if self.settings else str(default)

    @Slot(object, object, str)
    def item_done(self, source, result, error):
        if source in self.sources:
            item = self.files.item(self.sources.index(source))
            item.setText(("Échec · " if error else "OK · ") + source.name)
            item.setToolTip(error or str(result.destination))
        if error:
            self.status.setText(error)
        else:
            self.status.setText(f"Enregistré : {result.destination}")

    @Slot()
    def cancel_export(self):
        if self.job:
            self.job.requestInterruption()
            self.status.setText("Annulation après l’image en cours…")

    @Slot()
    def export_finished(self):
        job = self.job
        unprocessed = len(job.plan) - job.completed
        message = f"{job.successes} image(s) enregistrée(s) · {len(job.errors)} erreur(s)."
        if unprocessed:
            message += f" {unprocessed} image(s) non traitée(s)."
        if job.errors:
            # Keep the bar compact; every error stays readable in the tooltip and the summary screen.
            message += "\n" + job.errors[0]
            if len(job.errors) > 1:
                message += f"\n… et {len(job.errors) - 1} autre(s), détaillée(s) au survol."
        elif job.successes:
            message += f"\nDossier : {job.plan[0][1].parent}"
        self.status.setText(message)
        self.status.setToolTip("\n".join(job.errors))
        self.last_export = {
            "successes": job.successes,
            "errors": list(job.errors),
            "completed": job.completed,
            "total": len(job.plan),
            "folder": job.plan[0][1].parent,
            "input_bytes": job.input_bytes,
            "output_bytes": job.output_bytes,
            "history_errors": list(job.history_errors),
        }
        job.deleteLater()
        self.job = None
        self.drop_zone.setEnabled(True)
        self.settings_panel.setEnabled(True)
        self.export.setEnabled(bool(self.sources))
        self.busy_changed.emit(False)
        if not self.shutting_down and not self.preview_payload:
            self.preview_timer.start()

    def resizeEvent(self, event):
        self.body.setDirection(
            QBoxLayout.Direction.TopToBottom if self.width() < 800 else QBoxLayout.Direction.LeftToRight
        )
        super().resizeEvent(event)

    def stop_timers(self):
        self.preview_timer.stop()

    def running(self):
        return self.job is not None or self.preview_job is not None
