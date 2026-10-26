"""Home page and tool shortcuts."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shrimpit.gui.navigation import Page
from shrimpit.gui.theme import icon
from shrimpit.gui.widgets import label, panel


class HomePage(QWidget):
    navigate = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 38, 30, 28)
        layout.setSpacing(24)
        layout.addSpacing(20)
        welcome = label("Bienvenue sur", "hero")
        brand = label("Shrimp'It", "heroBrand")
        tagline = label("Vos images, à la bonne taille.", "section")
        description = label(
            "Compressez vos fichiers pour les partager plus facilement,\n"
            "ou agrandissez leurs dimensions, sans intelligence artificielle.",
            "muted",
        )
        for text in (welcome, brand, tagline, description):
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(text)
        layout.addStretch(1)
        self.cards = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.cards.setSpacing(20)
        for title, description, action, symbol, index in [
            (
                "Compression",
                "Réduisez le poids de vos images et choisissez leur format de sortie.",
                "Compresser des images  →",
                "image",
                Page.COMPRESSION,
            ),
            (
                "Agrandissement",
                "Agrandissez vos images avec un facteur ou des dimensions personnalisées.",
                "Agrandir des images  →",
                "expand",
                Page.ENLARGEMENT,
            ),
        ]:
            card, box = panel()
            box.setContentsMargins(24, 24, 24, 24)
            badge = label("")
            badge.setFixedSize(58, 58)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setPixmap(icon(symbol).pixmap(58, 58))
            title_row = QHBoxLayout()
            title_row.setSpacing(16)
            title_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
            heading = label(title, "cardTitle")
            heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            title_row.addWidget(heading, 1)
            box.addLayout(title_row)
            box.addWidget(label(description, "muted"))
            box.addSpacing(12)
            button = QPushButton(action)
            button.setObjectName("primary")
            button.clicked.connect(lambda checked=False, i=index: self.navigate.emit(i))
            box.addWidget(button)
            self.cards.addWidget(card, 1)
        layout.addLayout(self.cards)
        layout.addStretch(1)
        # Stretches centre the dark plate under the cards.
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(
            label("100 % local   ·   Vos originaux sont conservés   ·   JPEG, PNG et WebP", "footnote", False)
        )
        footer.addStretch()
        layout.addLayout(footer)

    def resizeEvent(self, event):
        self.cards.setDirection(
            QBoxLayout.Direction.TopToBottom if self.width() < 720 else QBoxLayout.Direction.LeftToRight
        )
        super().resizeEvent(event)
