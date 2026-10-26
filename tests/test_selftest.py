"""Check the self-test used to validate packaged builds."""

import pytest

from shrimpit import selftest
from shrimpit.__main__ import install_french_translation


@pytest.fixture
def french(qt_application):
    translator = install_french_translation(qt_application)
    assert translator is not None
    yield
    qt_application.removeTranslator(translator)


def test_self_test_passes_and_writes_a_report(qt_application, french, tmp_path):
    report = tmp_path / "report.txt"
    assert selftest.run_self_test(qt_application, report) == 0
    text = report.read_text(encoding="utf-8")
    assert text.count("OK ") == len(selftest.CHECKS)
    assert "Résultat : réussi" in text


def test_self_test_reports_each_failure(qt_application, french, tmp_path, monkeypatch):
    monkeypatch.setattr(selftest, "BACKGROUND", tmp_path / "missing.png")
    report = tmp_path / "report.txt"
    assert selftest.run_self_test(qt_application, report) == 1
    text = report.read_text(encoding="utf-8")
    assert "ÉCHEC  Ressources de l’application" in text
    assert "missing.png" in text
    assert "1 échec(s)" in text
