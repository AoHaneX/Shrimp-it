"""Shared page headings."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
)

from shrimpit.gui.theme import icon
from shrimpit.gui.widgets import label


def page_heading(layout, title, description, symbol):
    row = QHBoxLayout()
    row.setSpacing(16)
    badge = label("")
    badge.setFixedSize(58, 58)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setPixmap(icon(symbol).pixmap(58, 58))
    row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
    heading = label(title, "title")
    heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(heading, 1)
    layout.addLayout(row)
    layout.addWidget(label(description, "muted"))
