"""Output format, enlargement and file naming controls shared by both tools."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from shrimpit.engine import SUFFIXES
from shrimpit.errors import ConversionError
from shrimpit.filenames import validate_filename
from shrimpit.gui.upscale_controls import UpscaleControls
from shrimpit.gui.widgets import label
from shrimpit.preferences import integer_setting
from shrimpit.processing import Options, expand_name_template, suggested_name

MODE_NOTES = {
    "photo": "Photographie : Lanczos. La netteté ne recrée pas les détails absents.",
    "illustration": "Illustration : comparez les contours avec les deux interpolations.",
    "pixel_art": "Pixel Art : pixels nets, PNG et facteurs entiers uniquement. Aucun lissage.",
}


class OutputSettings(QWidget):
    """Build processing options and the output name template for the selected image."""

    changed = Signal()

    def __init__(self, enlarge=False, settings=None):
        super().__init__()
        self.enlarge = enlarge
        self.source = None
        self.source_size = None
        self.name_template = None
        self.pixel_mode = False
        self.updating = False
        self._previous_format = "PNG"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(label("02   Réglages", "section"))
        self.upscale_controls = UpscaleControls()
        self.upscale_controls.setVisible(enlarge)
        layout.addWidget(self.upscale_controls)
        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.format = QComboBox()
        self.format.addItems(["PNG", "JPEG", "WebP"])
        self.format.setCurrentText("PNG" if enlarge else "JPEG")
        self.format.setAccessibleName("Format de sortie")
        self.quality = QSpinBox()
        self.quality.setRange(1, 95)
        self.quality.setAccessibleName("Qualité JPEG ou WebP")
        self.quality.setValue(95 if enlarge else integer_setting(settings, "quality", 80, 1, 95))
        form.addRow("Format de sortie", self.format)
        form.addRow("Qualité JPEG / WebP", self.quality)
        self.factor = QComboBox()
        for scale in (2, 3, 4):
            self.factor.addItem(f"×{scale}", scale)
        self.factor.addItem("Dimensions personnalisées", None)
        if settings:
            self.set_default_scale(integer_setting(settings, "scale", 2, 2, 4))
        form.addRow("Agrandissement", self.factor)
        form.setRowVisible(self.factor, enlarge)
        layout.addLayout(form)

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
        layout.addWidget(self.custom)
        self.note = label("", "muted")
        layout.addWidget(self.note)
        layout.addWidget(label("Modèle de nom pour toutes les images", "muted"))
        self.filename = QLineEdit()
        self.filename.setAccessibleName("Modèle de nom pour toutes les images")
        self.filename.setPlaceholderText("[original name]-x2.png" if enlarge else "[original name]-min.jpg")
        self.filename.editingFinished.connect(self.store_name)
        self.filename.textEdited.connect(self.store_name)
        layout.addWidget(self.filename)
        layout.addWidget(
            label(
                "[original name] reprend le nom sans extension de chaque image. "
                "Ajoutez un préfixe ou un suffixe ; les doublons seront numérotés.",
                "muted",
            )
        )
        self.name_example = label("", "muted")
        layout.addWidget(self.name_example)

        self.format.currentTextChanged.connect(self.options_changed)
        self.quality.valueChanged.connect(self.changed)
        self.factor.currentIndexChanged.connect(self.options_changed)
        self.width_input.valueChanged.connect(lambda: self.dimensions_changed(True))
        self.height_input.valueChanged.connect(lambda: self.dimensions_changed(False))
        self.keep_ratio.toggled.connect(lambda: self.dimensions_changed(True))
        self.upscale_controls.changed.connect(self.upscale_changed)
        self.options_changed()

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

    def set_default_scale(self, scale):
        index = self.factor.findData(scale)
        self.factor.setCurrentIndex(max(index, 0))

    def set_source(self, source, size):
        """Follow the selected image: its size drives custom dimensions and the name example."""
        self.source, self.source_size = source, size
        if source is not None:
            self.updating = True
            if self.factor.currentData() is not None:
                self.width_input.setValue(size[0] * 2)
                self.height_input.setValue(size[1] * 2)
            elif self.keep_ratio.isChecked():
                self.height_input.setValue(max(1, round(self.width_input.value() * size[1] / size[0])))
            self.updating = False
        self.refresh_name_template()

    @Slot()
    def upscale_changed(self):
        pixel_art = self.enlarge and self.upscale_controls.mode.currentData() == "pixel_art"
        self.format.blockSignals(True)
        self.factor.blockSignals(True)
        if pixel_art and not self.pixel_mode:
            self._previous_format = self.format.currentText()
            self.format.setCurrentText("PNG")
        elif self.pixel_mode and not pixel_art:
            self.format.setCurrentText(self._previous_format)
        if pixel_art and self.factor.currentData() is None:
            self.factor.setCurrentIndex(0)
        self.format.setEnabled(not pixel_art)
        # Pixel Art only repeats pixels, so custom dimensions (last entry) are unavailable.
        self.factor.model().item(self.factor.count() - 1).setEnabled(not pixel_art)
        self.pixel_mode = pixel_art
        self.factor.blockSignals(False)
        self.format.blockSignals(False)
        self.options_changed()

    @Slot()
    def options_changed(self):
        if self.updating:
            return
        self.custom.setVisible(self.enlarge and self.factor.currentData() is None)
        self.quality.setEnabled(self.format.currentText() != "PNG")
        text = (
            "Agrandissement sans IA · Sortie jusqu’à 400 MP, selon la RAM disponible."
            if self.enlarge
            else "Dimensions conservées. Le poids peut augmenter."
        )
        text += " Fond blanc en JPEG." if self.format.currentText() == "JPEG" else " Transparence conservée."
        text += " Métadonnées retirées."
        if self.enlarge:
            text = MODE_NOTES[self.upscale_controls.mode.currentData()] + " " + text
            if self.factor.currentData() is None and self.keep_ratio.isChecked():
                text += " La largeur choisie s’applique au lot ; chaque image conserve ses proportions."
        self.note.setText(text)
        extension = SUFFIXES[self.format.currentText().upper()]
        if self.name_template is not None:
            try:
                validate_filename(self.name_template)
            except ConversionError:
                pass
            else:
                self.name_template = str(Path(self.name_template).with_suffix(extension))
        self.refresh_name_template()
        self.changed.emit()

    def dimensions_changed(self, width_changed):
        if self.updating:
            return
        if self.keep_ratio.isChecked() and self.source:
            width, height = self.source_size
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
        size = self.source_size if self.source else (self.width_input.value(), self.height_input.value())
        proposed = suggested_name(source, self.options(), size)
        return "[original name]" + proposed[len(source.stem) :]

    def refresh_name_template(self):
        self.filename.setText(
            self.default_name_template() if self.name_template is None else self.name_template
        )
        self.update_name_example()

    def output_name(self, source, size, options=None):
        options = options or self.options()
        if self.name_template is None:
            return suggested_name(source, options, size)
        return expand_name_template(source, self.name_template, options.output_format)

    def update_name_example(self):
        try:
            if self.source:
                name = self.output_name(self.source, self.source_size)
            else:
                name = expand_name_template(
                    Path("photo.png"), self.filename.text(), self.options().output_format
                )
            self.name_example.setText(f"Exemple : {name}")
        except ConversionError as exc:
            self.name_example.setText(str(exc))
