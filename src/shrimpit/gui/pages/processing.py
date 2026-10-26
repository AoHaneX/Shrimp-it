"""Image selection, processing controls, and previews."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from shrimpit.engine import EXTENSIONS, SUFFIXES
from shrimpit.errors import ConversionError
from shrimpit.examples import example_preview
from shrimpit.filenames import validate_filename
from shrimpit.gui.comparison import ComparisonPreview
from shrimpit.gui.pages.common import page_heading
from shrimpit.gui.theme import icon
from shrimpit.gui.upscale_controls import UpscaleControls
from shrimpit.gui.widgets import DropZone, PreviewCard, label, panel
from shrimpit.gui.workers import ExportJob, PreviewJob
from shrimpit.preferences import integer_setting
from shrimpit.processing import (
    Options,
    expand_name_template,
    export_plan,
    image_info,
    readable_size,
    suggested_name,
)


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
        self.name_template = None
        self.job = None
        self.preview_job = None
        self.revision = 0
        self.preview_payload = None
        self.updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 24, 22, 22)
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
        controls.addWidget(label("02   Réglages", "section"))
        self.upscale_controls = UpscaleControls()
        self.upscale_controls.setVisible(enlarge)
        controls.addWidget(self.upscale_controls)
        self._pixel_mode = False
        self._previous_format = "PNG"
        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.format = QComboBox()
        self.format.addItems(["PNG", "JPEG", "WebP"])
        self.format.setCurrentText("PNG" if enlarge else "JPEG")
        self.quality = QSpinBox()
        self.quality.setRange(1, 95)
        self.quality.setAccessibleName("Qualité JPEG ou WebP")
        self.format.setAccessibleName("Format de sortie")
        self.quality.setValue(95 if enlarge else integer_setting(settings, "quality", 80, 1, 95))
        form.addRow("Format de sortie", self.format)
        form.addRow("Qualité JPEG / WebP", self.quality)
        self.factor = QComboBox()
        for scale in (2, 3, 4):
            self.factor.addItem(f"×{scale}", scale)
        self.factor.addItem("Dimensions personnalisées", None)
        if settings:
            index = self.factor.findData(integer_setting(settings, "scale", 2, 2, 4))
            self.factor.setCurrentIndex(max(index, 0))
        form.addRow("Agrandissement", self.factor)
        form.setRowVisible(self.factor, enlarge)
        controls.addLayout(form)

        self.custom = QWidget()
        custom_layout = QVBoxLayout(self.custom)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        dimensions = QHBoxLayout()
        self.width_input, self.height_input = QSpinBox(), QSpinBox()
        for widget in (self.width_input, self.height_input):
            widget.setRange(1, 100000)
            widget.setSuffix(" px")
        self.width_input.setValue(1600)
        self.height_input.setValue(1200)
        self.width_input.setAccessibleName("Largeur de sortie")
        self.height_input.setAccessibleName("Hauteur de sortie")
        dimensions.addWidget(self.width_input, 1)
        separator = label("×", wrap=False)
        separator.setFixedWidth(18)
        separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dimensions.addWidget(separator)
        dimensions.addWidget(self.height_input, 1)
        custom_layout.addLayout(dimensions)
        self.keep_ratio = QCheckBox("Conserver les proportions")
        self.keep_ratio.setChecked(True)
        custom_layout.addWidget(self.keep_ratio)
        controls.addWidget(self.custom)
        self.note = label("", "muted")
        controls.addWidget(self.note)
        controls.addWidget(label("Modèle de nom pour toutes les images", "muted"))
        self.filename = QLineEdit()
        self.filename.setAccessibleName("Modèle de nom pour toutes les images")
        self.filename.setPlaceholderText("[original name]-x2.png" if enlarge else "[original name]-min.jpg")
        self.filename.editingFinished.connect(self.store_name)
        self.filename.textEdited.connect(self.store_name)
        controls.addWidget(self.filename)
        controls.addWidget(
            label(
                "[original name] reprend le nom sans extension de chaque image. "
                "Ajoutez un préfixe ou un suffixe ; les doublons seront numérotés.",
                "muted",
            )
        )
        self.name_example = label("", "muted")
        controls.addWidget(self.name_example)
        self.body.addWidget(self.settings_panel, 2)
        layout.addLayout(self.body)
        self.export = QPushButton("Agrandir et enregistrer…" if enlarge else "Compresser et enregistrer…")
        self.export.setObjectName("action")
        self.export.clicked.connect(self.start_export)
        self.export.setEnabled(False)
        layout.addWidget(self.export)
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_row.addWidget(self.progress, 1)
        self.percentage = label("0 %", "muted", False)
        progress_row.addWidget(self.percentage)
        self.cancel = QPushButton("Annuler la suite")
        self.cancel.clicked.connect(self.cancel_export)
        self.cancel.hide()
        progress_row.addWidget(self.cancel)
        layout.addLayout(progress_row)
        self.status = label(
            "Prêt à agrandir votre image." if enlarge else "Prêt à compresser vos images.", "status"
        )
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        layout.addStretch()

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(350)
        self.preview_timer.timeout.connect(self.start_preview)
        self.format.currentTextChanged.connect(self.options_changed)
        self.quality.valueChanged.connect(self.schedule_preview)
        self.factor.currentIndexChanged.connect(self.options_changed)
        self.width_input.valueChanged.connect(lambda: self.dimensions_changed(True))
        self.height_input.valueChanged.connect(lambda: self.dimensions_changed(False))
        self.keep_ratio.toggled.connect(lambda: self.dimensions_changed(True))
        self.upscale_controls.changed.connect(self.upscale_changed)
        self.options_changed()

    @property
    def source(self):
        row = self.files.currentRow()
        return self.sources[row] if 0 <= row < len(self.sources) else None

    def options(self):
        custom = self.enlarge and self.factor.currentData() is None
        size = (self.width_input.value(), self.height_input.value()) if custom else None
        return Options(
            self.enlarge,
            self.format.currentText().upper(),
            self.quality.value(),
            self.factor.currentData() or 2,
            size,
            self.keep_ratio.isChecked(),
            self.upscale_controls.settings(),
        )

    @Slot()
    def upscale_changed(self):
        pixel_art = self.enlarge and self.upscale_controls.mode.currentData() == "pixel_art"
        self.format.blockSignals(True)
        self.factor.blockSignals(True)
        if pixel_art and not self._pixel_mode:
            self._previous_format = self.format.currentText()
            self.format.setCurrentText("PNG")
        elif self._pixel_mode and not pixel_art:
            self.format.setCurrentText(self._previous_format)
        if pixel_art and self.factor.currentData() is None:
            self.factor.setCurrentIndex(0)
        self.format.setEnabled(not pixel_art)
        self.factor.model().item(3).setEnabled(not pixel_art)
        self._pixel_mode = pixel_art
        self.factor.blockSignals(False)
        self.format.blockSignals(False)
        self.options_changed()

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
        self.status.setText("\n".join(errors) if errors else f"{len(self.sources)} image(s) prête(s).")

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
            self.updating = True
            if self.factor.currentData() is not None:
                self.width_input.setValue(info.size[0] * 2)
                self.height_input.setValue(info.size[1] * 2)
            elif self.keep_ratio.isChecked():
                self.height_input.setValue(
                    max(1, round(self.width_input.value() * info.size[1] / info.size[0]))
                )
            self.updating = False

        else:
            self.info.setText("Aucune image sélectionnée")
        self.refresh_name_template()
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

    @Slot()
    def options_changed(self):
        if self.updating:
            return
        self.custom.setVisible(self.enlarge and self.factor.currentData() is None)
        self.quality.setEnabled(self.format.currentText() != "PNG" and self.job is None)
        text = (
            "Agrandissement sans IA · Sortie jusqu’à 400 MP, selon la RAM disponible."
            if self.enlarge
            else "Dimensions conservées. Le poids peut augmenter."
        )
        text += " Fond blanc en JPEG." if self.format.currentText() == "JPEG" else " Transparence conservée."
        self.note.setText(text + " Métadonnées retirées.")
        if self.enlarge:
            mode = self.upscale_controls.mode.currentData()
            descriptions = {
                "photo": "Photographie : Lanczos. La netteté ne recrée pas les détails absents.",
                "illustration": "Illustration : comparez les contours avec les deux interpolations.",
                "pixel_art": "Pixel Art : pixels nets, PNG et facteurs entiers uniquement. Aucun lissage.",
            }
            self.note.setText(descriptions[mode] + " " + self.note.text())
        for card in (self.before, self.after):
            card.canvas.pixel_art = self._pixel_mode
            card.canvas.update()
        self.comparison.canvas.pixel_art = self._pixel_mode
        self.comparison.canvas.update()
        if self.enlarge and self.factor.currentData() is None and self.keep_ratio.isChecked():
            self.note.setText(
                self.note.text()
                + " La largeur choisie s’applique au lot ; chaque image conserve ses proportions."
            )
        extension = SUFFIXES[self.format.currentText().upper()]
        if self.name_template is not None:
            try:
                validate_filename(self.name_template)
            except ConversionError:
                pass
            else:
                self.name_template = str(Path(self.name_template).with_suffix(extension))
        self.refresh_name_template()
        self.schedule_preview()

    def dimensions_changed(self, width_changed):
        if self.updating:
            return
        if self.keep_ratio.isChecked() and self.source:
            width, height = self.infos[self.source].size
            self.updating = True
            if width_changed:
                self.height_input.setValue(max(1, round(self.width_input.value() * height / width)))
            else:
                self.width_input.setValue(max(1, round(self.height_input.value() * width / height)))
            self.updating = False
        self.options_changed()

    @Slot()
    def store_name(self):
        name = self.filename.text()
        self.name_template = None if name == self.default_name_template() else name
        self.update_name_example()

    def default_name_template(self):
        source = self.source or Path("image.png")
        size = (
            self.infos[source].size if self.source else (self.width_input.value(), self.height_input.value())
        )
        proposed = suggested_name(source, self.options(), size)
        return "[original name]" + proposed[len(source.stem) :]

    def refresh_name_template(self):
        self.filename.setText(
            self.default_name_template() if self.name_template is None else self.name_template
        )
        self.update_name_example()

    def output_name(self, source, options=None):
        options = options or self.options()
        if self.name_template is None:
            return self.proposed_name(source, options)
        return expand_name_template(source, self.name_template, options.output_format)

    def update_name_example(self):
        try:
            if self.source:
                name = self.output_name(self.source)
                self.name_example.setText(f"Exemple : {name}")
            else:
                name = expand_name_template(
                    Path("photo.png"), self.filename.text(), self.options().output_format
                )
                self.name_example.setText(f"Exemple : {name}")
        except ConversionError as exc:
            self.name_example.setText(str(exc))

    def proposed_name(self, source, options=None):
        return suggested_name(source, options or self.options(), self.infos[source].size)

    def clear_images(self):
        if self.job:
            return
        self.sources.clear()
        self.infos.clear()
        self.files.clear()
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
        self.store_name()
        options = self.options()
        try:
            if len(self.sources) == 1:
                source = self.sources[0]
                name = self.output_name(source, options)
                validate_filename(name)
                extensions = sorted(EXTENSIONS[options.output_format])
                filename, _ = QFileDialog.getSaveFileName(
                    self,
                    "Enregistrer l’image",
                    str(source.parent / name),
                    f"{self.format.currentText()} ({' '.join('*' + e for e in extensions)})",
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
                        f"{self.format.currentText()}. Utilisez {' ou '.join(extensions)}."
                    )
                if destination.exists():
                    raise ConversionError(
                        f"{destination.name} existe déjà. Les fichiers existants ne sont jamais "
                        "remplacés : choisissez un autre nom."
                    )
                plan = [(source, destination)]
            else:
                initial = (
                    str(self.settings.value("output_folder", str(self.sources[0].parent)))
                    if self.settings
                    else str(self.sources[0].parent)
                )
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
        self.job.progress.connect(self.show_progress)
        self.job.finished.connect(self.export_finished)
        self.drop_zone.setEnabled(False)
        self.settings_panel.setEnabled(False)
        self.export.setEnabled(False)
        self.cancel.show()
        self.cancel.setEnabled(True)
        self.progress.setRange(0, 0)
        self.percentage.setText("…")
        self.status.setText("Traitement en cours…")
        self.busy_changed.emit(True)
        self.job.start()

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

    @Slot(int, int)
    def show_progress(self, completed, total):
        self.progress.setRange(0, total)
        self.progress.setValue(completed)
        self.percentage.setText(f"{round(100 * completed / total)} %")

    @Slot()
    def cancel_export(self):
        if self.job:
            self.job.requestInterruption()
            self.cancel.setEnabled(False)
            self.status.setText("Annulation après l’image en cours…")

    @Slot()
    def export_finished(self):
        job = self.job
        unprocessed = len(job.plan) - job.completed
        message = f"{job.successes} image(s) enregistrée(s) · {len(job.errors)} erreur(s)."
        if unprocessed:
            message += f" {unprocessed} image(s) non traitée(s)."
        if job.errors:
            message += "\n" + "\n".join(job.errors)
        elif job.successes:
            message += f"\nDossier : {job.plan[0][1].parent}"
        self.status.setText(message)
        self.progress.setRange(0, len(job.plan))
        self.progress.setValue(job.completed)
        self.percentage.setText(f"{round(100 * job.completed / len(job.plan))} %")
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
        self.quality.setEnabled(self.format.currentText() != "PNG")
        self.export.setEnabled(bool(self.sources))
        self.cancel.hide()
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
