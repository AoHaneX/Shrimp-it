"""Reusable painted backgrounds, drop zones, and image previews."""

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QBitmap, QColor, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from shrimpit.gui.theme import icon
from shrimpit.resources import BACKGROUND, SIDEBAR_COLLAPSED_WIDTH, SIDEBAR_EXPANDED_WIDTH


def label(text: str, role: str = "", wrap: bool = True) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def panel(role: str = "panel"):
    frame = QFrame()
    frame.setObjectName(role)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(12)
    return frame, layout


def paint_checkerboard(painter: QPainter, area: QRect | QRectF):
    """Paint the transparency pattern shown behind previews."""
    area = QRectF(area).toRect()
    painter.save()
    painter.setClipRect(area)
    for x in range(area.left(), area.right() + 1, 12):
        for y in range(area.top(), area.bottom() + 1, 12):
            dark = ((x - area.left()) // 12 + (y - area.top()) // 12) % 2
            painter.fillRect(x, y, 12, 12, QColor("#234259" if dark else "#173247"))
    painter.restore()


class OceanBackground(QWidget):
    def __init__(self, filename=BACKGROUND, sidebar=False):
        super().__init__()
        self.background = QPixmap(str(filename))
        self.sidebar = sidebar
        self._scaled = QPixmap()
        self._content_rect = QRect()
        if sidebar and not self.background.isNull():
            # Ignore nearly invisible pixels when locating the mascot's feet.
            mask = self.background.toImage().createAlphaMask(Qt.ImageConversionFlag.ThresholdAlphaDither)
            self._content_rect = QRegion(QBitmap.fromImage(mask)).boundingRect()
        self.setAutoFillBackground(False)

    def resizeEvent(self, event):
        width = SIDEBAR_EXPANDED_WIDTH if self.sidebar else self.width()
        mode = (
            Qt.AspectRatioMode.KeepAspectRatio
            if self.sidebar
            else Qt.AspectRatioMode.KeepAspectRatioByExpanding
        )
        self._scaled = self.background.scaled(
            width, self.height(), mode, Qt.TransformationMode.FastTransformation
        )
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.sidebar:
            self.paint_mascot(painter)
            return
        painter.fillRect(self.rect(), QColor("#00192d"))
        if not self._scaled.isNull():
            # Keep the left rock visible when the window becomes narrower.
            painter.drawPixmap(0, (self.height() - self._scaled.height()) // 2, self._scaled)

    def paint_mascot(self, painter):
        scene = self.parentWidget()
        if self.width() <= SIDEBAR_COLLAPSED_WIDTH or self._content_rect.isEmpty():
            return
        if not isinstance(scene, OceanBackground) or scene._scaled.isNull():
            return
        # Use the same coordinates as the ocean to keep Shrimpy on the rock.
        ocean = scene._scaled
        width = ocean.width() * 0.025
        height = width * self._content_rect.height() / self._content_rect.width()
        origin = self.mapTo(scene, self.rect().topLeft())
        x = ocean.width() * 0.065 - width / 2 - origin.x()
        bottom = (scene.height() - ocean.height()) // 2 + ocean.height() * 0.765 - origin.y()
        # Slide in from the left using the sidebar animation's current width.
        progress = (self.width() - SIDEBAR_COLLAPSED_WIDTH) / (
            SIDEBAR_EXPANDED_WIDTH - SIDEBAR_COLLAPSED_WIDTH
        )
        progress = max(0.0, min(1.0, progress))
        x = -width + (x + width) * progress
        target = QRectF(x, bottom - height, width, height)
        buttons = getattr(self, "buttons", [])
        if buttons and target.top() < buttons[-1].geometry().bottom() + 12:
            return
        painter.drawPixmap(target, self.background, QRectF(self._content_rect))


class DropZone(QFrame):
    files_dropped = Signal(list)
    choose_clicked = Signal()

    def __init__(self, multiple: bool):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        upload = QLabel()
        upload.setPixmap(icon("upload").pixmap(44, 44))
        upload.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(upload)
        text = "Glissez-déposez une ou plusieurs images ici" if multiple else "Glissez-déposez une image ici"
        heading = label(text, "section")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        hint = label("ou choisissez un fichier sur votre ordinateur", "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.choose = QPushButton("Choisir des images…" if multiple else "Choisir une image…")
        self.choose.setObjectName("primary")
        self.choose.setIcon(icon("folder", "#ffffff"))
        self.choose.clicked.connect(self.choose_clicked)
        layout.addWidget(self.choose, alignment=Qt.AlignmentFlag.AlignCenter)
        types = label("JPEG, PNG ou WebP · Traitement local, sans IA", "muted")
        types.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(types)

    def set_hover(self, value):
        self.setProperty("hover", value)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if (
            self.isEnabled()
            and event.mimeData().hasUrls()
            and any(u.isLocalFile() for u in event.mimeData().urls())
        ):
            event.acceptProposedAction()
            self.set_hover(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.set_hover(False)
        event.accept()

    def dropEvent(self, event):
        self.set_hover(False)
        if self.isEnabled():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
                event.acceptProposedAction()


class PreviewCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()
        self.pixel_art = False
        self.setMinimumHeight(165)

    def set_image(self, data: bytes | None):
        self.pixmap = QPixmap()
        if data:
            self.pixmap.loadFromData(data)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#09223a"))
        if self.pixmap.isNull():
            painter.setPen(QColor("#879ebb"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Aucune image")
            return
        scaled = self.pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
            if self.pixel_art
            else Qt.TransformationMode.SmoothTransformation,
        )
        target = QRect(
            (self.width() - scaled.width()) // 2,
            (self.height() - scaled.height()) // 2,
            scaled.width(),
            scaled.height(),
        )
        paint_checkerboard(painter, target)
        painter.drawPixmap(target.topLeft(), scaled)


class PreviewCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.image_size = (0, 0)
        self.setObjectName("preview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.heading = label(title)
        layout.addWidget(self.heading)
        self.canvas = PreviewCanvas()
        layout.addWidget(self.canvas, 1)
        self.details = label("—", "muted")
        layout.addWidget(self.details)

    def clear(self):
        self.image_size = (0, 0)
        self.canvas.set_image(None)
        self.details.setText("—")

    def display(self, data, size, weight):
        self.image_size = size
        self.canvas.set_image(data)
        self.details.setText(f"{size[0]} × {size[1]} px · {weight}")
