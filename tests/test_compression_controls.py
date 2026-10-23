"""Check that compression controls keep their existing meaning."""

from PySide6.QtCore import QSettings

from shrimpit.gui.main_window import MainWindow


def test_quality_control_and_format_switching(qt_application, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    page = window.compression
    try:
        assert page.format.currentText() == "JPEG"
        assert page.quality.value() == 80
        assert (page.quality.minimum(), page.quality.maximum()) == (1, 95)
        page.quality.setValue(72)
        for label, enabled in (("PNG", False), ("WebP", True), ("JPEG", True)):
            page.format.setCurrentText(label)
            assert page.quality.isEnabled() == enabled
            assert page.options().quality == 72
            assert page.options().output_format == label.upper()
            assert page.options().enlarge is False
        assert "poids peut augmenter" in page.note.text()
        assert "Fond blanc" in page.note.text()
    finally:
        page.stop_timers()
        window.enlargement.stop_timers()
        window.close()
