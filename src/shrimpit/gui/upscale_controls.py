"""Controls for enlargement modes and optional photo sharpening."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QSpinBox,
    QWidget,
)

from shrimpit.upscale import UpscaleSettings


class UpscaleControls(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.mode = QComboBox()
        for text, value in (
            ("Photographie", "photo"),
            ("Illustration", "illustration"),
            ("Pixel Art", "pixel_art"),
        ):
            self.mode.addItem(text, value)
        self.mode.setAccessibleName("Mode d’agrandissement")
        self.form.addRow("Type d’image", self.mode)
        self.interpolation = QComboBox()
        self.interpolation.addItem("Bicubic · contours doux", "bicubic")
        self.interpolation.addItem("Lanczos · détails plus marqués", "lanczos")
        self.interpolation.setAccessibleName("Interpolation pour les illustrations")
        self.form.addRow("Interpolation", self.interpolation)
        self.sharpen = QCheckBox("Ajouter une netteté légère")
        self.sharpen.setChecked(True)
        self.form.addRow(self.sharpen)
        self.details = QPushButton("Réglages de netteté")
        self.details.setCheckable(True)
        self.form.addRow(self.details)
        self.amount = QSpinBox()
        self.amount.setRange(0, 100)
        self.amount.setValue(40)
        self.amount.setSuffix(" %")
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0.5, 2.0)
        self.radius.setSingleStep(0.1)
        self.radius.setDecimals(1)
        self.radius.setValue(0.8)
        self.radius.setSuffix(" px")
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 10)
        self.threshold.setValue(3)
        for title, control, hint in (
            ("Intensité", self.amount, "Une valeur faible limite les contours accentués."),
            ("Rayon", self.radius, "Largeur des détails accentués, en pixels de sortie."),
            ("Seuil", self.threshold, "Un seuil plus élevé évite d’accentuer les petites variations."),
        ):
            control.setAccessibleName("Netteté : " + title)
            control.setToolTip(hint)
            self.form.addRow(title, control)
            control.valueChanged.connect(self.changed)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.sharpen.toggled.connect(self.refresh)
        self.interpolation.currentIndexChanged.connect(self.changed)
        self.details.toggled.connect(self.update_visibility)
        self.refresh()

    def refresh(self):
        self.update_visibility()
        self.changed.emit()

    def update_visibility(self):
        photo = self.mode.currentData() == "photo"
        self.form.setRowVisible(self.interpolation, self.mode.currentData() == "illustration")
        self.form.setRowVisible(self.sharpen, photo)
        self.form.setRowVisible(self.details, photo and self.sharpen.isChecked())
        self.details.setText("Masquer les réglages" if self.details.isChecked() else "Réglages de netteté")
        for control in (self.amount, self.radius, self.threshold):
            self.form.setRowVisible(control, photo and self.sharpen.isChecked() and self.details.isChecked())

    def settings(self):
        return UpscaleSettings(
            mode=self.mode.currentData(),
            illustration_filter=self.interpolation.currentData(),
            sharpen=self.sharpen.isChecked(),
            radius=self.radius.value(),
            amount=self.amount.value(),
            threshold=self.threshold.value(),
        )
