"""Compare two previews in one coordinate system without changing image data."""

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QSlider, QVBoxLayout, QWidget

from shrimpit.gui.widgets import label


class ComparisonCanvas(QWidget):
    position_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.before = QPixmap()
        self.after = QPixmap()
        self.before_size = QSize()
        self.after_size = QSize()
        self.position = 50
        self.pixel_art = False
        self.message = "Calcul de l’aperçu…"
        self.setMinimumHeight(260)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SplitHCursor)
        self.setAccessibleName("Comparaison avant après")
        self.setToolTip(
            "Glissez la séparation. Flèches gauche/droite au clavier ; Début/Fin pour tout révéler."
        )

    def set_images(self, before, after, before_size, after_size):
        self.before, self.after = before, after
        self.before_size, self.after_size = QSize(*before_size), QSize(*after_size)
        self.update()

    def set_position(self, position):
        position = max(0, min(100, position))
        if self.position != position:
            self.position = position
            self.position_changed.emit(position)
            self.update()

    def image_rect(self, size):
        area = QRectF(self.rect()).adjusted(8, 32, -8, -8)
        reference = self.before_size if not self.before_size.isEmpty() else size
        if size.isEmpty() or reference.isEmpty():
            return area
        scale = min(area.width() / reference.width(), area.height() / reference.height())
        frame = QRectF(0, 0, reference.width() * scale, reference.height() * scale)
        frame.moveCenter(area.center())
        scale = min(frame.width() / size.width(), frame.height() / size.height())
        target = QRectF(0, 0, size.width() * scale, size.height() * scale)
        target.moveCenter(frame.center())
        return target

    def split_x(self):
        frame = self.image_rect(self.before_size)
        return frame.left() + frame.width() * self.position / 100

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#09223a"))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not self.pixel_art)
        frame = self.image_rect(self.before_size)
        if self.before.isNull():
            painter.setPen(QColor("#acbce4"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        painter.save()
        painter.setClipRect(frame)
        for x in range(int(frame.left()), int(frame.right()) + 1, 12):
            for y in range(int(frame.top()), int(frame.bottom()) + 1, 12):
                color = (
                    "#234259"
                    if ((x - int(frame.left())) // 12 + (y - int(frame.top())) // 12) % 2
                    else "#173247"
                )
                painter.fillRect(x, y, 12, 12, QColor(color))
        painter.restore()
        split = self.split_x()
        for pixmap, size, clip in (
            (
                self.before,
                self.before_size,
                QRectF(frame.left(), frame.top(), split - frame.left(), frame.height()),
            ),
            (self.after, self.after_size, QRectF(split, frame.top(), frame.right() - split, frame.height())),
        ):
            painter.save()
            painter.setClipRect(clip)
            if not pixmap.isNull():
                painter.drawPixmap(self.image_rect(size), pixmap, QRectF(pixmap.rect()))
            else:
                painter.fillRect(clip, QColor("#09223a"))
                painter.setPen(QColor("#acbce4"))
                painter.drawText(clip, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            painter.restore()
        painter.setPen(QColor("#e8edff"))
        painter.drawText(QRectF(12, 4, 100, 24), Qt.AlignmentFlag.AlignLeft, "Avant")
        painter.drawText(QRectF(self.width() - 112, 4, 100, 24), Qt.AlignmentFlag.AlignRight, "Après")
        if not self.after.isNull():
            painter.setPen(QPen(QColor("#20dafa"), 2))
            painter.drawLine(int(split), int(frame.top()), int(split), int(frame.bottom()))
            painter.setBrush(QColor("#08253d"))
            painter.drawRoundedRect(QRectF(split - 16, frame.center().y() - 20, 32, 40), 8, 8)
            center_x, center_y = int(split), int(frame.center().y())
            for direction in (-1, 1):
                edge = center_x + direction * 9
                inner = center_x + direction * 4
                painter.drawLine(inner, center_y - 5, edge, center_y)
                painter.drawLine(edge, center_y, inner, center_y + 5)

    def move_divider(self, x):
        if self.before.isNull() or self.after.isNull():
            return
        frame = self.image_rect(self.before_size)
        if frame.width() > 0:
            self.set_position(round(100 * (x - frame.left()) / frame.width()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.move_divider(event.position().x())
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move_divider(event.position().x())
            event.accept()

    def keyPressEvent(self, event):
        if self.before.isNull() or self.after.isNull():
            return super().keyPressEvent(event)
        positions = {
            Qt.Key.Key_Left: self.position - 1,
            Qt.Key.Key_Right: self.position + 1,
            Qt.Key.Key_Home: 0,
            Qt.Key.Key_End: 100,
        }
        if event.key() in positions:
            self.set_position(positions[event.key()])
            event.accept()
        else:
            super().keyPressEvent(event)


class ComparisonPreview(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = ComparisonCanvas()
        layout.addWidget(self.canvas, 1)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.setAccessibleName("Position de la séparation avant après")
        self.slider.setToolTip("0 : tout après · 100 : tout avant")
        self.slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #163c5a; height: 6px; border-radius: 3px; }"
            "QSlider::sub-page:horizontal { background: #16c7ea; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #20dafa; border: 1px solid #93eeff;"
            " width: 14px; margin: -5px 0; border-radius: 7px; }"
            "QSlider::handle:horizontal:disabled { background: #43617a; border-color: #43617a; }"
        )
        self.slider.valueChanged.connect(self.canvas.set_position)
        self.canvas.position_changed.connect(self.slider.setValue)
        layout.addWidget(self.slider)
        row = QHBoxLayout()
        self.before_details = label("", "muted")
        self.after_details = label("", "muted")
        row.addWidget(self.before_details, 1)
        row.addWidget(self.after_details, 1)
        layout.addLayout(row)
        self.ratio_note = label("Proportions différentes : images centrées, sans déformation.", "muted")
        self.ratio_note.hide()
        layout.addWidget(self.ratio_note)

    def display(self, before, after, before_size, after_size, before_details, after_details):
        self.canvas.set_images(before, after, before_size, after_size)
        self.slider.setEnabled(not before.isNull() and not after.isNull())
        self.before_details.setText("Avant · " + before_details)
        self.after_details.setText("Après · " + after_details)
        self.ratio_note.setVisible(
            not after.isNull() and before_size[0] * after_size[1] != before_size[1] * after_size[0]
        )
