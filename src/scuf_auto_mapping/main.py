from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from pathlib import Path

from scuf_auto_mapping.infrastructure.repository_sqlite import Repository
from scuf_auto_mapping.infrastructure.system import configure_logging, data_directory


def self_test() -> int:
    from PySide6.QtCore import qVersion
    from scuf_auto_mapping.domain.models import Profile
    from scuf_auto_mapping.infrastructure.import_export import export_profiles, load_profiles

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        repo = Repository(root / "test.db")
        profile = Profile("Smoke test", "game.exe", "Expected smoke profile")
        repo.save(profile)
        export_profiles(root / "profiles.json", repo.profiles())
        assert load_profiles(root / "profiles.json")[0] == profile
        repo.close()
    print(f"SCUF Automatic Mapping 0.1.0 self-test passed; Qt {qVersion()}; hardware unverified")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--diagnostics" in sys.argv:
        return self_test()
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from scuf_auto_mapping.ui.window import Window

    app = QApplication.instance() or QApplication(sys.argv)
    if "--gui-smoke" in sys.argv:
        from PySide6.QtCore import QTimer

        with tempfile.TemporaryDirectory() as temporary:
            smoke_repo = Repository(Path(temporary) / "smoke.db")
            window = Window(smoke_repo, start_worker=False)
            window.show()
            QTimer.singleShot(300, window.close)
            result = app.exec()
            smoke_repo.close()
            return result
    app.setApplicationName("SCUF Automatic Mapping")
    app.setOrganizationName("SCUFAutomaticMapping")
    directory = data_directory()
    configure_logging(directory)
    lock = QLockFile(str(directory / "application.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(
            None,
            "Already running",
            "SCUF Automatic Mapping is already running. Check the system tray.",
        )
        return 0

    def report(kind, value, traceback) -> None:
        logging.error("Unhandled application error", exc_info=(kind, value, traceback))
        QMessageBox.critical(
            None,
            "Application error",
            f"{value}\nLocal logs were saved. Your database has not been reset.",
        )

    sys.excepthook = report
    if sys.platform != "win32":
        QMessageBox.information(
            None,
            "Unsupported platform",
            "Windows 10/11 is required for foreground detection. Library editing is available here.",
        )
    path = directory / "profiles.db"
    repo: Repository | None = None
    try:
        repo = Repository(path)
        repo.profiles()
        repo.settings()
    except Exception as exc:
        if repo is not None:
            repo.close()
        logging.exception("Database could not be opened")
        # Preserve original bytes before offering an explicit new database.
        preserved = directory / "profiles.unreadable.db"
        if path.exists():
            if preserved.exists():
                import uuid

                preserved = directory / f"profiles.unreadable-{uuid.uuid4().hex}.db"
            shutil.copy2(path, preserved)
        choice = QMessageBox.question(
            None,
            "Database recovery required",
            f"Cannot read database: {exc}\nOriginal preserved at {preserved}.\n"
            "Start a new empty database? Original bytes remain in the preserved backup.\n"
            "Restore later using a JSON export or known-good database backup.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            lock.unlock()
            return 1
        # Only replace after explicit recovery confirmation and preservation of original bytes.
        if path.exists():
            path.unlink()
        repo = Repository(path)
    try:
        window = Window(repo)
        app.aboutToQuit.connect(window.shutdown)
        window.show()
        return app.exec()
    finally:
        repo.close()
        lock.unlock()
