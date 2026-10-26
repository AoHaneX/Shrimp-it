"""User preferences and application information."""

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from shrimpit import __version__
from shrimpit.diagnostics import log_directory
from shrimpit.gui.pages.common import page_heading
from shrimpit.gui.widgets import label, panel
from shrimpit.preferences import boolean_setting, integer_setting


class SettingsPage(QWidget):
    animation_changed = Signal(bool)
    quality_changed = Signal(int)
    scale_changed = Signal(int)

    def __init__(self, settings):
        super().__init__()
        self.setObjectName("page")
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(24)
        page_heading(layout, "Paramètres", "Personnalisez vos réglages de départ.", "settings")
        card, box = panel()
        box.addWidget(label("Valeurs par défaut", "section"))
        form = QFormLayout()
        self.quality = QSpinBox()
        self.quality.setRange(1, 95)
        self.quality.setValue(integer_setting(settings, "quality", 80, 1, 95))
        self.scale = QComboBox()
        for value in (2, 3, 4):
            self.scale.addItem(f"×{value}", value)
        self.scale.setCurrentIndex(max(0, self.scale.findData(integer_setting(settings, "scale", 2, 2, 4))))
        form.addRow("Qualité de compression", self.quality)
        form.addRow("Facteur d’agrandissement", self.scale)
        box.addLayout(form)
        box.addWidget(
            label("Ces valeurs s’appliquent aussitôt aux pages Compression et Agrandissement.", "muted")
        )
        self.animation = QCheckBox("Animer l’ouverture du menu")
        self.animation.setChecked(boolean_setting(settings, "animation"))
        box.addWidget(self.animation)
        self.sound = QCheckBox("Jouer le son de fin de traitement")
        self.sound.setChecked(boolean_setting(settings, "sound"))
        self.sound.toggled.connect(lambda value: settings.setValue("sound", value))
        box.addWidget(self.sound)
        self.notifications = QCheckBox("Afficher les notifications du système")
        self.notifications.setChecked(boolean_setting(settings, "notifications"))
        self.notifications.toggled.connect(lambda value: settings.setValue("notifications", value))
        box.addWidget(self.notifications)
        self.quality.valueChanged.connect(lambda value: settings.setValue("quality", value))
        self.quality.valueChanged.connect(self.quality_changed)
        self.scale.currentIndexChanged.connect(self.store_scale)
        self.animation.toggled.connect(lambda value: settings.setValue("animation", value))
        self.animation.toggled.connect(self.animation_changed)
        layout.addWidget(card)
        about, about_layout = panel()
        about_layout.addWidget(label(f"Shrimp'It · version {__version__}", "section"))
        about_layout.addWidget(label("Vos images restent sur votre ordinateur", "section"))
        about_layout.addWidget(
            label(
                "Aucun envoi sur Internet. Compression et interpolation Pillow sans IA.\n"
                "JPEG, PNG et WebP · Entrée : 25 MP ; agrandissement : jusqu’à 400 MP selon la RAM.\n"
                "Aperçu automatique jusqu’à 25 MP.\n"
                "Les originaux et les fichiers déjà présents sont protégés.",
                "muted",
            )
        )
        layout.addWidget(about)
        self.logs = QPushButton("Ouvrir le dossier des diagnostics")
        self.logs.clicked.connect(self.open_logs)
        layout.addWidget(self.logs)
        layout.addStretch()

    def store_scale(self):
        scale = self.scale.currentData()
        self.settings.setValue("scale", scale)
        self.scale_changed.emit(scale)

    def open_logs(self):
        folder = log_directory()
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            self.logs.setToolTip("Aucun diagnostic disponible pour le moment.")
