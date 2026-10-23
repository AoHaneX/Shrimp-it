"""Animated sidebar navigation independent of image processing."""

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from shrimpit.gui.theme import icon
from shrimpit.gui.widgets import OceanBackground, label
from shrimpit.resources import (
    SHRIMPY_ICON,
    SIDEBAR_COLLAPSED_WIDTH,
    SIDEBAR_EXPANDED_WIDTH,
    SIDEBAR_MASCOT,
)


def navigation_icon(symbol):
    # Offset the artwork down by two logical pixels to match the text visually.
    canvas = QPixmap(100, 116)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    artwork = (
        icon(symbol, "#bdcaff")
        .pixmap(64, 64)
        .scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    )
    painter.drawPixmap(0, 16, artwork)
    painter.end()
    return QIcon(canvas)


class Sidebar(OceanBackground):
    selected = Signal(int)

    def __init__(self):
        super().__init__(SIDEBAR_MASCOT, sidebar=True)
        self.expanded = True
        self.setFixedWidth(SIDEBAR_EXPANDED_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 20)
        layout.setSpacing(8)
        self.menu = QPushButton()
        self.menu.setObjectName("menu")
        self.menu.setIcon(icon("menu", "#eef3ff"))
        self.menu.setIconSize(QSize(26, 26))
        self.menu.setFixedSize(42, 42)
        self.menu.setToolTip("Réduire / ouvrir le menu")
        self.menu.setAccessibleName("Réduire ou ouvrir le menu")
        self.menu.clicked.connect(self.toggle)
        layout.addWidget(self.menu)
        layout.addSpacing(22)
        self.brand_header = QWidget()
        branding = QHBoxLayout(self.brand_header)
        branding.setContentsMargins(0, 0, 0, 0)
        branding.setSpacing(8)
        self.logo = QLabel()
        self.logo.setFixedSize(78, 78)
        self.logo.setPixmap(
            QPixmap(str(SHRIMPY_ICON)).scaled(
                78, 78, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self.brand = label("Shrimp'It", "brand", False)
        self.brand.setStyleSheet("font-size: 32px;")
        branding.addWidget(self.logo)
        branding.addWidget(self.brand, 1)
        layout.addWidget(self.brand_header)
        layout.addSpacing(26)
        self.names = ["Accueil", "Compression", "Agrandissement", "Historique", "Paramètres"]
        self.page_indices = [0, 1, 2, 5, 3]
        self.buttons = []
        for name, symbol, index in zip(
            self.names, ["home", "image", "expand", "history", "settings"], self.page_indices
        ):
            button = QPushButton("  " + name)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setIcon(navigation_icon(symbol))
            button.setIconSize(QSize(25, 29))
            button.setFixedHeight(52)
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.clicked.connect(lambda checked=False, i=index: self.selected.emit(i))
            self.buttons.append(button)
            layout.addWidget(button)
        layout.addStretch()
        self.animation = QPropertyAnimation(self, b"panelWidth", self)
        self.animation.setDuration(190)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.finished.connect(self.restore_labels)
        self.set_page(0)

    def get_width(self):
        return self.width()

    def set_width(self, value):
        self.setFixedWidth(value)

    panelWidth = Property(int, get_width, set_width)

    def toggle(self):
        self.animation.stop()
        self.expanded = not self.expanded
        self.brand_header.hide()
        for button in self.buttons:
            button.setText("")
        self.animation.setStartValue(self.width())
        self.animation.setEndValue(SIDEBAR_EXPANDED_WIDTH if self.expanded else SIDEBAR_COLLAPSED_WIDTH)
        self.animation.start()

    def restore_labels(self):
        self.brand_header.setVisible(self.expanded)
        for button, name in zip(self.buttons, self.names):
            button.setText("  " + name if self.expanded else "")

    def set_page(self, index):
        for i, button in zip(self.page_indices, self.buttons):
            button.setChecked(i == index)
