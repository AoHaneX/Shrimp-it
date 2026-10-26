"""Ocean palette, replaceable icons, and optional title font."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBitmap, QColor, QFontDatabase, QIcon, QPainter, QPen, QPixmap, QPolygonF, QRegion

from shrimpit.resources import ASSETS, TITLE_FONT


def title_font() -> str:
    path = TITLE_FONT
    font_id = QFontDatabase.addApplicationFont(str(path)) if path.exists() else -1
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    return families[0] if families else "Consolas"


def icon(name: str, color: str = "#26d6ff") -> QIcon:
    """Prefer a supplied PNG and otherwise draw a small vector icon."""
    path = ASSETS / "icons" / f"{name}.png"
    if path.exists():
        source = QPixmap(str(path))
        if not source.isNull():
            # Center the visible artwork instead of its transparent margins.
            mask = source.toImage().createAlphaMask(Qt.ImageConversionFlag.ThresholdAlphaDither)
            bounds = QRegion(QBitmap.fromImage(mask)).boundingRect()
            if not bounds.isEmpty():
                source = source.copy(bounds)
            source = source.scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            canvas = QPixmap(64, 64)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            painter.drawPixmap((64 - source.width()) // 2, (64 - source.height()) // 2, source)
            painter.end()
            return QIcon(canvas)
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if name in {"image", "eye"}:
        painter.drawRoundedRect(QRectF(10, 10, 44, 44), 3, 3)
        painter.drawEllipse(QPointF(41, 23), 4, 4)
        painter.drawPolyline(
            QPolygonF([QPointF(14, 46), QPointF(26, 32), QPointF(36, 42), QPointF(44, 35), QPointF(52, 45)])
        )
    elif name == "home":
        painter.drawPolyline(QPolygonF([QPointF(8, 30), QPointF(32, 10), QPointF(56, 30)]))
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(16, 27),
                    QPointF(16, 54),
                    QPointF(27, 54),
                    QPointF(27, 39),
                    QPointF(38, 39),
                    QPointF(38, 54),
                    QPointF(48, 54),
                    QPointF(48, 27),
                ]
            )
        )
    elif name == "expand":
        for start, end in [((11, 53), (26, 38)), ((38, 26), (53, 11))]:
            painter.drawLine(*start, *end)
        painter.drawPolyline(QPolygonF([QPointF(11, 38), QPointF(11, 53), QPointF(26, 53)]))
        painter.drawPolyline(QPolygonF([QPointF(38, 11), QPointF(53, 11), QPointF(53, 26)]))
    elif name == "history":
        painter.drawEllipse(QRectF(10, 10, 44, 44))
        painter.drawPolyline(QPolygonF([QPointF(32, 18), QPointF(32, 32), QPointF(43, 38)]))
    elif name == "menu":
        for y in (16, 32, 48):
            painter.drawLine(15, y, 49, y)
    elif name == "upload":
        painter.drawArc(QRectF(8, 20, 22, 27), 90 * 16, 210 * 16)
        painter.drawArc(QRectF(20, 8, 29, 32), 0, 180 * 16)
        painter.drawArc(QRectF(39, 22, 18, 25), -90 * 16, 180 * 16)
        painter.drawLine(32, 57, 32, 28)
        painter.drawPolyline(QPolygonF([QPointF(22, 38), QPointF(32, 28), QPointF(42, 38)]))
    elif name == "folder":
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(9, 49),
                    QPointF(9, 15),
                    QPointF(26, 15),
                    QPointF(32, 23),
                    QPointF(52, 23),
                    QPointF(52, 30),
                ]
            )
        )
        painter.drawPolygon(QPolygonF([QPointF(9, 49), QPointF(19, 30), QPointF(58, 30), QPointF(49, 49)]))
    elif name == "close":
        painter.drawLine(17, 17, 47, 47)
        painter.drawLine(47, 17, 17, 47)
    else:
        painter.drawEllipse(QRectF(19, 19, 26, 26))
        for angle in range(0, 360, 45):
            painter.save()
            painter.translate(32, 32)
            painter.rotate(angle)
            painter.drawLine(0, 19, 0, 26)
            painter.restore()
    painter.end()
    return QIcon(pixmap)


def stylesheet(font: str) -> str:
    return f"""
    QWidget {{ color: #e8edff; font-family: 'Segoe UI'; font-size: 14px; }}
    QMainWindow, QScrollArea, QStackedWidget {{ background: transparent; border: none; }}
    QWidget#page {{ background: transparent; }}
    QLabel {{ background: transparent; border: none; }}
    QLabel#title {{ font-family: '{font}'; font-size: 34px; font-weight: bold; }}
    QLabel#hero {{ font-family: '{font}'; font-size: 50px; font-weight: bold; }}
    QLabel#heroBrand {{ font-family: '{font}'; font-size: 66px; font-weight: bold; color: #1ad9fa; }}
    QLabel#brand {{ font-family: '{font}'; font-size: 32px; font-weight: bold; }}
    QLabel#cardTitle {{ font-family: '{font}'; font-size: 29px; font-weight: bold; }}
    QLabel#status {{ background: rgba(2, 18, 34, 235); border: 1px solid #163d57; border-radius: 7px; padding: 11px; color: #bfcdec; }}
    QLabel#section {{ font-size: 19px; font-weight: 600; }}
    QLabel#muted {{ color: #acbce4; }}
    QLabel#cyan {{ color: #21dafa; font-weight: 600; }}
    QFrame#panel {{ background: rgba(2, 20, 38, 218); border: 1px solid #164969; border-radius: 15px; }}
    QFrame#preview {{ background: rgba(17, 44, 73, 225); border: 1px solid #204866; border-radius: 11px; }}
    QFrame#drop {{ background: rgba(3, 28, 53, 200); border: 1px dashed #1bdafa; border-radius: 14px; }}
    QFrame#drop[hover="true"] {{ background: rgba(5, 67, 96, 230); border: 2px solid #25ddff; }}
    QPushButton {{ background: #0a2a47; border: 1px solid #215777; border-radius: 9px; padding: 10px 14px; }}
    QPushButton:hover {{ background: #12476a; border-color: #23caec; }}
    QPushButton:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border: 1px solid #27e0ff; }}
    QPushButton#primary {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #08bfed,stop:1 #0876ff); border: 1px solid #19dcff; font-weight: 600; padding: 13px; }}
    QPushButton#primary:hover {{ background: #098ce9; }}
    QPushButton#action {{ background: #1bc5eb; color: #001a2a; border: 1px solid #24e2ff; font-weight: 700; padding: 14px; }}
    QPushButton:disabled, QPushButton#primary:disabled, QPushButton#action:disabled {{ background: #14354d; color: #7b92ad; border-color: #204762; }}
    QPushButton#removeImages {{ background: #782b38; color: #ffffff; border-color: #a34452; }}
    QPushButton#removeImages:hover {{ background: #b33542; border-color: #d65b66; }}
    QPushButton#removeImages:pressed {{ background: #5e202b; border-color: #a34452; }}
    QPushButton#removeImages:focus {{ border: 1px solid #ffbac2; }}
    QPushButton#removeImages:disabled {{ background: #382b35; color: #91818b; border-color: #51404b; }}
    QPushButton#nav {{ background: transparent; border: 1px solid transparent; text-align: left; padding: 13px 12px; font-size: 16px; }}
    QPushButton#nav:checked {{ background: rgba(6, 63, 102, 220); border: 1px solid #13caed; color: #27dcff; font-weight: 600; }}
    QPushButton#nav:hover {{ background: rgba(12, 54, 85, 210); }}
    QPushButton#menu {{ background: transparent; border: none; padding: 7px; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: #102b48; border: 1px solid #214967; border-radius: 7px; padding: 6px 9px; selection-background-color: #087cac; }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: #7088a6; }}
    QComboBox QAbstractItemView {{ background: #09243d; color: #e8edff; selection-background-color: #126184; }}
    QListWidget {{ background: transparent; border: 1px solid #214967; border-radius: 6px; outline: none; }}
    QListWidget::item {{ padding: 5px; }}
    QListWidget::item:selected {{ background: #114f70; color: #4ce3ff; }}
    QProgressBar {{ background: #112f4e; border: 1px solid #214967; border-radius: 7px; min-height: 13px; max-height: 13px; }}
    QProgressBar::chunk {{ background: #16c7ea; border-radius: 6px; }}
    QScrollBar:vertical {{ background: #061d30; width: 9px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #235b78; min-height: 24px; border-radius: 4px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{ background: #08253d; color: #d8eeff; border: 1px solid #2d718b; }}
    QCheckBox {{ spacing: 8px; }}
    QDialog, QMessageBox, QWidget#historyDetails {{ background: #061d30; }}
    QMessageBox QPushButton {{ min-width: 80px; }}
    QSlider::groove:horizontal {{ background: #163c5a; height: 6px; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: #16c7ea; border-radius: 3px; }}
    QSlider::handle:horizontal {{ background: #20dafa; border: 1px solid #93eeff; width: 14px; margin: -5px 0; border-radius: 7px; }}
    QSlider::handle:horizontal:disabled {{ background: #43617a; border-color: #43617a; }}
    QTreeWidget {{ background: #061d30; border: 1px solid #164969; border-radius: 10px; }}
    QTreeWidget::item {{ padding: 8px; }}
    QTreeWidget::item:selected {{ background: #114f70; }}
    QHeaderView::section {{ background: #102b48; padding: 10px; border: none; }}
    QScrollBar:horizontal {{ background: #061d30; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: #235b78; min-width: 24px; border-radius: 4px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """
