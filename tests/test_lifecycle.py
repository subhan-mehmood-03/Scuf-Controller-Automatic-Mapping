import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from scuf_auto_mapping import main as entry
from scuf_auto_mapping.domain.models import Settings
from scuf_auto_mapping.infrastructure.repository_sqlite import Repository
from scuf_auto_mapping.ui.window import Worker


def test_worker_shutdown(qtbot):
    worker = Worker()
    worker.settings = Settings(interval_ms=250)
    with qtbot.waitSignal(worker.snapshot, timeout=3000):
        worker.start()
    worker.requestInterruption()
    assert worker.wait(2000)


def test_recovery_preserves_original(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["scuf-auto-mapping"])
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(entry, "data_directory", lambda: tmp_path)
    monkeypatch.setattr(entry, "configure_logging", lambda *_: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *_: QMessageBox.StandardButton.Ok)
    path = tmp_path / "profiles.db"
    path.write_bytes(b"corrupt original data")
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    assert entry.main() == 1
    assert path.read_bytes() == b"corrupt original data"
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QApplication, "exec", lambda *_: 0)
    monkeypatch.setattr(QCoreApplication, "exec", lambda *_: 0)
    from scuf_auto_mapping.ui import window

    class FakeWindow:
        def __init__(self, repo):
            repo.save_settings(Settings(onboarding_complete=True))

        def show(self):
            pass

        def shutdown(self):
            pass

    monkeypatch.setattr(window, "Window", FakeWindow)
    assert entry.main() == 0
    backups = list(tmp_path.glob("profiles.unreadable*.db"))
    assert backups and all(p.read_bytes() == b"corrupt original data" for p in backups)
    repo = Repository(path)
    assert repo.settings().onboarding_complete
    repo.close()
