"""Browse local export batches and their original metadata."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shrimpit.gui.history_thumbnails import ThumbnailLoader
from shrimpit.gui.widgets import label
from shrimpit.history import HistoryError
from shrimpit.processing import readable_size


def local_date(value):
    return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y à %H:%M:%S")


def parameter_text(entry):
    parameters = entry["parameters"]
    lines = [f"Format : {parameters.get('output_format', '—')}"]
    if parameters.get("output_format") != "PNG":
        lines.append(f"Qualité : {parameters.get('quality', '—')}")
    if entry["operation"] == "upscale":
        settings = parameters.get("upscale", {})
        mode = settings.get("mode")
        names = {"photo": "Photographie", "illustration": "Illustration", "pixel_art": "Pixel Art"}
        lines.append(f"Mode : {names.get(mode, mode)}")
        if parameters.get("size"):
            lines.append(f"Dimensions personnalisées : {' × '.join(map(str, parameters['size']))} px")
            lines.append(f"Proportions conservées : {'oui' if parameters.get('keep_ratio') else 'non'}")
        else:
            lines.append(f"Facteur : ×{parameters.get('scale', '—')}")
        if mode == "photo":
            lines.append("Interpolation : Lanczos")
            lines.append(f"Netteté : {'activée' if settings.get('sharpen') else 'désactivée'}")
            if settings.get("sharpen"):
                lines.append(
                    f"Rayon : {settings.get('radius')} · Intensité : {settings.get('amount')} % · "
                    f"Seuil : {settings.get('threshold')}"
                )
        elif mode == "illustration":
            lines.append(f"Interpolation : {settings.get('illustration_filter', '—')}")
        else:
            lines.append("Interpolation : Nearest Neighbor · Sans netteté supplémentaire")
    for key, title in (("input_size", "Dimensions avant"), ("output_size", "Dimensions après")):
        if key in parameters:
            lines.append(f"{title} : {' × '.join(map(str, parameters[key]))} px")
    return "\n".join(lines)


class HistoryDetails(QDialog):
    def __init__(self, page, batch, entry):
        super().__init__(page)
        self.page, self.batch, self.entry = page, batch, entry
        self.token = uuid4().hex
        self.setWindowTitle("Détails du traitement")
        self.resize(740, 720)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("historyDetails")
        body = QVBoxLayout(content)
        self.previews = {}
        self.open_buttons = {}
        for kind, title in (("source", "Image originale"), ("destination", "Image générée")):
            path = Path(entry[kind])
            body.addWidget(label(title, "section"))
            preview = label("Chargement…", "muted")
            preview.setFixedHeight(180)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.addWidget(preview)
            self.previews[kind] = preview
            text = label(f"{path.name}\n{path}")
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body.addWidget(text)
            button = QPushButton("Ouvrir l’emplacement du fichier")
            button.setEnabled(path.is_file())
            button.clicked.connect(lambda checked=False, k=kind: self.open_location(k))
            self.open_buttons[kind] = button
            body.addWidget(button)
        operation = "Agrandissement" if entry["operation"] == "upscale" else "Compression"
        body.addWidget(
            label(
                f"{operation} · {local_date(entry['created_at'])}\n"
                f"Avant : {readable_size(entry['input_bytes'])} → Après : {readable_size(entry['output_bytes'])}\n"
                f"Lot : {batch['id']}",
                "muted",
            )
        )
        body.addWidget(label("Paramètres utilisés", "section"))
        body.addWidget(label(parameter_text(entry)))
        scroll.setWidget(content)
        layout.addWidget(scroll)
        actions = QHBoxLayout()
        self.delete_button = QPushButton("Supprimer de l’historique")
        self.delete_button.clicked.connect(self.remove_entry)
        actions.addWidget(self.delete_button)
        close = QPushButton("Fermer")
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        page.loader.signals.ready.connect(self.thumbnail_ready)
        for kind in self.previews:
            page.loader.request((self.token, kind), entry[kind])

    def thumbnail_ready(self, token, image, status):
        if token[0] != self.token:
            return
        preview = self.previews[token[1]]
        if image.isNull():
            preview.setText(status)
        else:
            preview.setPixmap(QPixmap.fromImage(image))

    def open_location(self, kind):
        path = Path(self.entry[kind])
        if not path.is_file():
            self.open_buttons[kind].setEnabled(False)
            self.previews[kind].clear()
            self.previews[kind].setText("Image introuvable")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))):
            QMessageBox.warning(
                self, "Ouverture impossible", f"Impossible d’ouvrir le dossier :\n{path.parent}"
            )

    def remove_entry(self):
        if self.page.mutate(lambda: self.page.store.delete_entry(self.batch["id"], self.entry["id"])):
            self.accept()


class HistoryPage(QWidget):
    def __init__(self, store):
        super().__init__()
        self.setObjectName("page")
        self.store = store
        self.loader = ThumbnailLoader(self)
        self.loader.signals.ready.connect(self.thumbnail_ready)
        self.generation = 0
        self.items = {}
        self.batches_by_id = {}
        self.entries_by_id = {}
        self.expanded_ids = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label("Historique", "title"))
        layout.addWidget(
            label("Retrouvez vos traitements par lot. Les images restent à leur emplacement.", "muted")
        )
        self.clear_button = QPushButton("Effacer tout l’historique")
        self.clear_button.clicked.connect(self.clear_history)
        layout.addWidget(self.clear_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.status = label("", "muted")
        layout.addWidget(self.status)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Image originale", "→ Image générée", "Taille / Action"])
        self.tree.setIconSize(QSize(80, 60))
        self.tree.setWordWrap(True)
        self.tree.header().setMinimumSectionSize(200)
        self.tree.setMinimumHeight(350)
        for column in (0, 1):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemExpanded.connect(self.expand_batch)
        self.tree.itemCollapsed.connect(self.collapse_batch)
        self.tree.itemClicked.connect(self.open_entry)
        self.tree.itemActivated.connect(self.open_entry)
        layout.addWidget(self.tree, 1)
        self.reload()

    def reload(self):
        self.generation += 1
        self.loader.pool.clear()
        self.items.clear()
        self.batches_by_id.clear()
        self.entries_by_id.clear()
        self.tree.clear()
        try:
            batches = self.store.batches()
        except HistoryError as exc:
            # Clearing replaces an unreadable file, so keep it available as a way out.
            self.status.setText(str(exc))
            self.clear_button.setEnabled(True)
            return
        self.status.setText(
            self.store.warning
            or (
                f"{len(batches)} lot(s) · Dépliez un lot puis cliquez sur une image pour voir ses détails."
                if batches
                else "Aucun traitement dans l’historique"
            )
        )
        self.clear_button.setEnabled(bool(batches))
        for batch in batches:
            self.batches_by_id[batch["id"]] = batch
            self.entries_by_id.update({entry["id"]: entry for entry in batch["images"]})
            operations = {entry["operation"] for entry in batch["images"]}
            operation = "Agrandissement" if operations == {"upscale"} else "Compression"
            item = QTreeWidgetItem(
                [local_date(batch["created_at"]), f"{operation} · {len(batch['images'])} image(s)"]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, batch["id"])
            self.tree.addTopLevelItem(item)
            QTreeWidgetItem(item, ["Déplier pour charger les images…"])
            delete = QPushButton("Supprimer le lot")
            delete.clicked.connect(lambda checked=False, b=batch: self.delete_batch(b))
            self.tree.setItemWidget(item, 2, delete)
            item.setSizeHint(0, QSize(200, delete.sizeHint().height() + 16))
            if batch["id"] in self.expanded_ids:
                item.setExpanded(True)

    def collapse_batch(self, item):
        batch_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(batch_id, str):
            self.expanded_ids.discard(batch_id)

    def expand_batch(self, item):
        batch_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(batch_id, str):
            return
        batch = self.batches_by_id[batch_id]
        self.expanded_ids.add(batch["id"])
        if item.data(1, Qt.ItemDataRole.UserRole):
            return
        item.setData(1, Qt.ItemDataRole.UserRole, True)
        item.takeChildren()
        self.add_entries(item, batch, 0, self.generation)

    def add_entries(self, parent, batch, offset, generation):
        if generation != self.generation:
            return
        for entry in batch["images"][offset : offset + 20]:
            item = QTreeWidgetItem(
                parent,
                [
                    Path(entry["source"]).name,
                    "→ " + Path(entry["destination"]).name,
                    f"{readable_size(entry['input_bytes'])} → {readable_size(entry['output_bytes'])}",
                ],
            )
            item.setData(0, Qt.ItemDataRole.UserRole, (batch["id"], entry["id"]))
            for column, kind in enumerate(("source", "destination")):
                token = (generation, entry["id"], column)
                self.items[token] = item
                item.setToolTip(column, entry[kind])
                self.loader.request(token, entry[kind])
        if offset + 20 < len(batch["images"]):
            QTimer.singleShot(20, lambda: self.add_entries(parent, batch, offset + 20, generation))

    def thumbnail_ready(self, token, image, status):
        item = self.items.get(token)
        if item is None:
            return
        column = token[2]
        if image.isNull():
            item.setText(column, item.text(column) + "\n" + status)
        else:
            item.setIcon(column, QIcon(QPixmap.fromImage(image)))

    def open_entry(self, item, column=0):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple):
            dialog = HistoryDetails(self, self.batches_by_id[data[0]], self.entries_by_id[data[1]])
            dialog.exec()
            dialog.deleteLater()

    def mutate(self, action):
        try:
            action()
        except HistoryError as exc:
            QMessageBox.warning(self, "Historique", str(exc))
            return False
        self.reload()
        return True

    def confirm(self, text):
        return (
            QMessageBox.question(
                self,
                "Supprimer de l’historique ?",
                text + "\nLes images sur le disque seront conservées.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def delete_batch(self, batch):
        if self.confirm(f"Retirer ce lot de {len(batch['images'])} image(s) ?"):
            self.mutate(lambda: self.store.delete_batch(batch["id"]))

    def clear_history(self):
        if self.confirm("Effacer tout l’historique des traitements ?"):
            self.mutate(self.store.clear)

    def shutdown(self):
        self.generation += 1
        self.items.clear()
        self.loader.stop()
