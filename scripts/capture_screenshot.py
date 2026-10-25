"""Render the actual UI with synthetic demo data; no personal process information."""

import tempfile
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from scuf_auto_mapping.domain.matcher import Match
from scuf_auto_mapping.domain.models import Foreground, Profile, now
from scuf_auto_mapping.infrastructure.repository_sqlite import Repository
from scuf_auto_mapping.ui.window import Window

app = QApplication([])
# The Windows offscreen Qt plugin does not enumerate system fonts reliably.
font_path = Path("C:/Windows/Fonts/segoeui.ttf")
if font_path.exists():
    QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Segoe UI", 10))
with tempfile.TemporaryDirectory() as temporary:
    repo = Repository(Path(temporary) / "demo.db")
    profile = Profile(
        "Example game (demo data)",
        "ExampleGame.exe",
        "Competitive paddles",
        r"C:\Games\Example\ExampleGame.exe",
    )
    repo.save(profile)
    window = Window(repo, start_worker=False)
    window.show()
    window.on_snapshot(
        (
            Foreground(profile.executable_path, profile.executable_name),
            Match(profile),
            True,
            "unknown",
            "",
            now(),
            False,
        )
    )
    app.processEvents()
    Path("docs/images").mkdir(parents=True, exist_ok=True)
    window.grab().save("docs/images/dashboard.png")
    window.nav.setCurrentRow(2)
    app.processEvents()
    window.grab().save("docs/images/setup.png")
    window.close()
    repo.close()
