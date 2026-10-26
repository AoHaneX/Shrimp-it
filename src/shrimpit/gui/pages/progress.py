"""Animated export screen and access to completed files."""

from PySide6.QtCore import QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QMovie, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget

from shrimpit.gui.widgets import label, panel
from shrimpit.processing import readable_size
from shrimpit.resources import PROCESSING_ANIMATIONS, SHRIMPY_ICON


class ProgressPage(QWidget):
    cancel_requested = Signal()
    return_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.movie = None
        self.folder = None
        self.plan = []
        self.running = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 16, 30, 16)

        card, box = panel()
        card.setMaximumWidth(820)
        box.setContentsMargins(26, 16, 26, 16)
        box.setSpacing(12)
        box.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.heading = label("Traitement en cours", "title")
        self.heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.heading)
        self.description = label("Vos images sont traitées sur votre ordinateur.", "muted")
        self.description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.description)
        self.animation = QLabel()
        self.animation.setFixedSize(220, 220)
        self.animation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.animation, alignment=Qt.AlignmentFlag.AlignCenter)
        box.addSpacing(12)
        self.current_file = label("", "cyan")
        self.current_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_file.setMinimumHeight(self.current_file.fontMetrics().height() + 8)
        box.addWidget(self.current_file)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        box.addWidget(self.progress)
        self.counter = label("", "muted")
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.counter)
        self.details = label("", "muted")
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.details)
        actions = QHBoxLayout()
        self.cancel = QPushButton("Annuler après l’image en cours")
        self.cancel.clicked.connect(self.request_cancel)
        actions.addWidget(self.cancel)
        self.open_folder = QPushButton("Ouvrir le dossier des résultats")
        self.open_folder.setObjectName("primary")
        self.open_folder.clicked.connect(self.reveal_folder)
        actions.addWidget(self.open_folder)
        self.back = QPushButton("Retour aux images")
        self.back.clicked.connect(self.return_requested)
        actions.addWidget(self.back)
        box.addLayout(actions)
        layout.addWidget(card)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

    def begin(self, job, enlarge: bool, animation_style: str):
        self.running = True
        self.plan = job.plan
        self.folder = None
        self.heading.setText("Agrandissement en cours" if enlarge else "Compression en cours")
        self.description.setText("Shrimpy s’occupe de vos images. Vos originaux sont conservés.")
        self.current_file.setText(job.plan[0][0].name)
        self.details.setText("Les résultats seront enregistrés dans le dossier choisi.")
        self.progress.setRange(0, 0)
        self.counter.setText(f"0 / {len(job.plan)} image(s) terminée(s)")
        self.cancel.show()
        self.cancel.setEnabled(True)
        self.open_folder.hide()
        self.back.hide()
        if self.movie:
            self.movie.stop()
            self.animation.setMovie(None)
            self.movie.deleteLater()
        path = PROCESSING_ANIMATIONS.get(animation_style, PROCESSING_ANIMATIONS["pixel"])
        self.movie = QMovie(str(path), parent=self)
        self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
        self.movie.setScaledSize(self.animation.size())
        if self.movie.isValid():
            self.animation.setMovie(self.movie)
            self.movie.start()
        else:
            self.show_static_mascot()
        job.progress.connect(self.update_progress)

    @Slot(int, int)
    def update_progress(self, completed, total):
        self.progress.setRange(0, total)
        self.progress.setValue(completed)
        self.counter.setText(
            f"{completed} / {total} image(s) terminée(s) · {round(100 * completed / total)} %"
        )
        if completed < len(self.plan):
            self.current_file.setText(self.plan[completed][0].name)

    @Slot()
    def request_cancel(self):
        if self.running:
            self.cancel.setEnabled(False)
            self.description.setText("L’image en cours sera terminée. Les suivantes ne seront pas traitées.")
            self.cancel_requested.emit()

    def show_static_mascot(self):
        self.animation.setPixmap(
            QPixmap(str(SHRIMPY_ICON)).scaled(
                QSize(200, 200),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def finish(self, summary):
        self.running = False
        if self.movie:
            self.movie.stop()
        self.show_static_mascot()
        remaining = summary["total"] - summary["completed"]
        if remaining:
            title = "Traitement interrompu"
        elif summary["errors"]:
            title = "Terminé avec des erreurs"
        else:
            title = "Vos images sont prêtes !"
        self.heading.setText(title)
        self.description.setText(
            "Les fichiers ont été enregistrés dans le dossier choisi."
            if summary["successes"]
            else "Aucun fichier n’a été enregistré. Consultez le bilan ci-dessous."
        )
        self.current_file.setText(f"{summary['successes']} image(s) enregistrée(s)")
        self.update_progress(summary["completed"], summary["total"])
        # Keep the completion message after updating the progress counter.
        self.current_file.setText(f"{summary['successes']} image(s) enregistrée(s)")
        self.folder = summary["folder"] if summary["successes"] else None
        lines = [f"Dossier : {self.folder}"] if self.folder else ["Aucun fichier de sortie créé."]
        if summary.get("input_bytes"):
            difference = summary["input_bytes"] - summary["output_bytes"]
            lines.append(
                f"Avant : {readable_size(summary['input_bytes'])} · Après : {readable_size(summary['output_bytes'])}"
            )
            lines.append(
                f"Gain : {readable_size(difference)}"
                if difference >= 0
                else f"Fichiers plus volumineux de {readable_size(-difference)}"
            )
        if remaining:
            lines.append(f"{remaining} image(s) non traitée(s).")
        lines.extend(summary["errors"])
        self.details.setText("\n".join(lines))
        self.cancel.hide()
        self.open_folder.setVisible(self.folder is not None)
        self.back.show()

    @Slot()
    def reveal_folder(self):
        if self.folder and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder))):
            self.details.setText(f"Impossible d’ouvrir automatiquement le dossier.\n{self.folder}")
