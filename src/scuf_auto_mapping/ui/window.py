from __future__ import annotations

import logging
import ntpath
import sys
import time
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scuf_auto_mapping.application.monitor_service import MonitorService
from scuf_auto_mapping.domain.matcher import warnings
from scuf_auto_mapping.domain.models import Foreground, Profile, Settings, now
from scuf_auto_mapping.infrastructure.foreground_win32 import WindowsForegroundProvider
from scuf_auto_mapping.infrastructure.import_export import export_profiles, load_profiles, preview
from scuf_auto_mapping.infrastructure.processes import ProcessStatusProvider, running_processes
from scuf_auto_mapping.infrastructure.repository_sqlite import Repository
from scuf_auto_mapping.infrastructure.system import (
    WindowsRegistry,
    export_diagnostics,
    set_autostart,
)

HELP = "https://help.corsair.com/hc/en-us/articles/360058672092-iCUE-How-to-Set-up-and-manage-profiles-in-iCUE-4-or-newer"


class Worker(QThread):
    snapshot = Signal(object)
    discovered = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.monitor = MonitorService(WindowsForegroundProvider())
        self.profiles: list[Profile] = []
        self.settings = Settings()
        self.paused = False
        self.discover = False

    def run(self) -> None:
        status = "unknown"
        icue_path = ""
        last_presence = 0.0
        while not self.isInterruptionRequested():
            try:
                settings, profiles = self.settings, self.profiles
                if self.monitor.paused != self.paused:
                    self.monitor.pause(self.paused)
                fg, result, changed = self.monitor.poll(profiles)
                if time.monotonic() - last_presence > 10:
                    presence = ProcessStatusProvider(settings.icue_names.split(","))
                    status = presence.get_process_status()
                    icue_path = presence.detected_path
                    last_presence = time.monotonic()
                if self.discover:
                    self.discover = False
                    self.discovered.emit(running_processes())
                self.snapshot.emit((fg, result, changed, status, icue_path, now(), self.paused))
            except Exception:
                logging.exception("Monitoring error")
            # Short interruptible waits permit prompt shutdown even at a long poll interval.
            for _ in range(max(1, self.settings.interval_ms // 50)):
                if self.isInterruptionRequested():
                    return
                self.msleep(50)


def button(label: str, action, layout) -> QPushButton:
    widget = QPushButton(label)
    widget.clicked.connect(action)
    layout.addWidget(widget)
    return widget


class ProfileDialog(QDialog):
    def __init__(
        self, parent: QWidget, profile: Profile | None = None, foreground: Foreground | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit game" if profile else "Add game")
        self.resize(620, 450)
        self.original = profile
        self.result_profile: Profile | None = None
        form = QFormLayout(self)
        self.fields: dict[str, QLineEdit] = {}
        for key, title in (
            ("game_name", "Game name"),
            ("executable_path", "Full executable path"),
            ("executable_name", "Executable basename (.exe)"),
            ("icue_profile_name", "Expected iCUE profile"),
            ("notes", "Notes"),
        ):
            field = QLineEdit(str(getattr(profile, key, "")))
            field.setMaxLength(
                10000 if key == "notes" else 32767 if key == "executable_path" else 256
            )
            field.setAccessibleName(title)
            self.fields[key] = field
            form.addRow(title, field)
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(profile.enabled if profile else True)
        form.addRow(self.enabled)
        button("Browse trusted game executable…", self.browse, form)
        if foreground and foreground.name:

            def use_foreground() -> None:
                self.fields["executable_path"].setText(foreground.path)
                self.fields["executable_name"].setText(foreground.name)

            button("Use foreground application", use_foreground, form)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        form.addRow(self.error)
        form.addRow(
            QLabel(
                "Choose the game itself, rather than its launcher. Missing files are allowed\n"
                "for incomplete discovery, and will be flagged in the library."
            )
        )
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        controls.accepted.connect(self.save)
        controls.rejected.connect(self.reject)
        form.addRow(controls)

    def use_path(self, path: str) -> None:
        self.fields["executable_path"].setText(path)
        self.fields["executable_name"].setText(ntpath.basename(path))

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose trusted game executable", "", "Executables (*.exe)"
        )
        if path:
            self.use_path(path)

    def save(self) -> None:
        try:
            values = self.original.to_dict() if self.original else {}
            values.update({key: field.text() for key, field in self.fields.items()})
            values.update(enabled=self.enabled.isChecked(), updated_at=now())
            if self.original and any(
                values[k] != getattr(self.original, k)
                for k in ("executable_path", "executable_name", "icue_profile_name")
            ):
                values.update(linked_app_attested_at=None, mapping_test_attested_at=None)
            self.result_profile = Profile(**values)
            self.accept()
        except (ValueError, TypeError) as exc:
            self.error.setText(str(exc))


class Window(QMainWindow):
    def __init__(self, repository: Repository, start_worker: bool = True) -> None:
        super().__init__()
        self.repo = repository
        self.settings = repository.settings()
        self.foreground = Foreground()
        self.icue_path = ""
        self.last_notification = 0.0
        self.last_notified_id = ""
        self.last_observation = "Not yet observed"
        self.presence = "unknown"
        self.exiting = False
        self.worker = Worker()
        self.worker.snapshot.connect(self.on_snapshot)
        self.worker.discovered.connect(self.show_discovery)
        self.setWindowTitle("SCUF Automatic Mapping")
        self.resize(1150, 760)
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#63d7c0"))
        self.setWindowIcon(QIcon(pixmap))
        container = QWidget()
        self.setCentralWidget(container)
        outer = QHBoxLayout(container)
        self.nav = QListWidget()
        self.nav.setAccessibleName("Navigation")
        self.nav.addItems(["Dashboard", "Games", "Setup", "Activity", "Settings", "About"])
        self.nav.setFixedWidth(170)
        self.pages = QStackedWidget()
        outer.addWidget(self.nav)
        outer.addWidget(self.pages, 1)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.build_dashboard()
        self.build_games()
        self.build_setup()
        self.build_activity()
        self.build_settings()
        self.build_about()
        self.nav.setCurrentRow(0)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu(self)
        for name, callback in (
            ("Restore", self.restore),
            ("Pause / resume", self.toggle_pause),
            ("Exit", self.exit_app),
        ):
            action = QAction(name, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.restore()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.refresh()
        self.setStyleSheet("""
            QWidget { background: #121923; color: #edf3fa; font-size: 14px; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox, QTableWidget { background: #202d3d; padding: 7px; }
            QPushButton { background: #284c57; padding: 9px; border-radius: 4px; }
            QPushButton:focus { border: 2px solid #63d7c0; }
            QPushButton:hover { background: #356575; }
            QListWidget::item { padding: 16px; }
            QListWidget::item:selected { background: #284c57; }
            QHeaderView::section { background: #284252; padding: 8px; }
            QLabel { padding: 3px; }
        """)
        if start_worker:
            self.worker.start()
            if not self.settings.onboarding_complete:
                QTimer.singleShot(200, self.onboarding)

    def page(self, title: str) -> QVBoxLayout:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 26px; font-weight: bold; color: #63d7c0")
        layout.addWidget(heading)
        self.pages.addWidget(page)
        return layout

    def build_dashboard(self) -> None:
        layout = self.page("Your game. Your expected mapping.")
        self.status = QLabel("Waiting for foreground observation…")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(self.status.textInteractionFlags())
        layout.addWidget(self.status)
        self.pause_button = button("Pause monitoring", self.toggle_pause, layout)
        button("Add foreground application", self.add_profile, layout)
        layout.addWidget(
            QLabel(
                "Source: iCUE native Linked App\nActual active iCUE profile: unknown\n"
                "Process detection does not prove controller connection or mapping activation."
            )
        )
        layout.addStretch()

    def build_games(self) -> None:
        layout = self.page("Games & profiles")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games, executables, profiles…")
        self.search.setAccessibleName("Search games")
        self.search.textChanged.connect(self.refresh_table)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Game", "EXE", "Expected profile", "iCUE link", "Hardware test", "Enabled", "ID"]
        )
        self.table.hideColumn(6)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_profile())
        layout.addWidget(self.table)
        row = QHBoxLayout()
        layout.addLayout(row)
        for label, callback in (
            ("Add", self.add_profile),
            ("Edit", self.edit_profile),
            ("Delete", self.delete_profile),
            ("Enable / disable", self.toggle_enabled),
            ("Discover running…", self.discover),
            ("Export…", self.export_json),
            ("Import…", self.import_json),
        ):
            button(label, callback, row)
        self.conflicts = QLabel()
        self.conflicts.setWordWrap(True)
        layout.addWidget(self.conflicts)

    def build_setup(self) -> None:
        layout = self.page("Set up native iCUE Linked App")
        self.setup_choice = QComboBox()
        self.setup_choice.setAccessibleName("Game to configure")
        self.setup_choice.currentIndexChanged.connect(self.load_attestations)
        layout.addWidget(self.setup_choice)
        guide = QLabel(
            "1. Connect Envision Pro using its supplied SLIPSTREAM USB receiver (not Bluetooth).\n"
            "2. In iCUE 5+, create a software profile with the exact name below.\n"
            "3. Configure paddles / SAX in software Mappings.\n"
            "4. Add the game's exact executable under that profile's Linked App. Check for existing conflicts in iCUE.\n"
            "5. Leave iCUE running; focus the game and test actual paddle behavior.\n\n"
            "Software mappings while iCUE runs differ from onboard slots. Saving onboard profiles requires USB-C.\n"
            "This assistant does not write iCUE configuration or command your controller."
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)
        self.setup_details = QLabel()
        self.setup_details.setWordWrap(True)
        layout.addWidget(self.setup_details)
        row = QHBoxLayout()
        layout.addLayout(row)
        for label, callback in (
            ("Copy executable path", lambda: self.copy_field("executable_path")),
            ("Copy profile name", lambda: self.copy_field("icue_profile_name")),
            ("Open executable folder", self.open_folder),
            ("Open detected iCUE", self.open_icue),
            ("Official guide", lambda: QDesktopServices.openUrl(QUrl(HELP))),
        ):
            button(label, callback, row)
        self.linked = QCheckBox("I linked this game in iCUE (user confirmation)")
        self.tested = QCheckBox("I validated paddle behavior in game (user confirmation)")
        layout.addWidget(self.linked)
        layout.addWidget(self.tested)
        button("Save confirmations", self.attest, layout)
        layout.addStretch()

    def build_activity(self) -> None:
        layout = self.page("Local activity")
        self.event_search = QLineEdit()
        self.event_search.setPlaceholderText("Search events")
        self.event_search.setAccessibleName("Search events")
        self.event_search.textChanged.connect(self.refresh_events)
        layout.addWidget(self.event_search)
        self.events = QTextEdit()
        self.events.setReadOnly(True)
        layout.addWidget(self.events)
        self.raw_diagnostics = QCheckBox(
            "Include raw full paths in diagnostics (contains personal directory names)"
        )
        layout.addWidget(self.raw_diagnostics)
        button("Export diagnostics…", self.diagnostics, layout)

    def build_settings(self) -> None:
        layout = self.page("Settings")
        form = QFormLayout()
        layout.addLayout(form)
        self.setting_widgets: dict[str, QWidget] = {}
        for name, value in asdict(self.settings).items():
            if name == "onboarding_complete":
                continue
            title = name.replace("_", " ").capitalize()
            widget: QCheckBox | QSpinBox | QLineEdit
            if isinstance(value, bool):
                widget = QCheckBox(title)
                widget.setChecked(value)
            elif isinstance(value, int):
                widget = QSpinBox()
                limits = {
                    "interval_ms": (250, 10000),
                    "retention_days": (1, 30),
                    "event_limit": (100, 5000),
                }
                widget.setRange(*limits[name])
                widget.setValue(value)
            else:
                widget = QLineEdit(value)
            widget.setAccessibleName(title)
            self.setting_widgets[name] = widget
            form.addRow(title, widget)
        layout.addWidget(
            QLabel(
                "Default profile is a reminder for unmatched apps; configure fallback behavior in iCUE manually.\n"
                "Autostart is opt-in and available only for the packaged Windows EXE.\n"
                "Process lists use comma-separated basenames. Notifications are off by default."
            )
        )
        button("Save settings", self.save_settings, layout)
        button("Back up database…", self.backup, layout)
        button("Show first-run guide", self.onboarding, layout)
        button(
            "Official iCUE download page",
            lambda: QDesktopServices.openUrl(QUrl("https://www.corsair.com/us/en/s/icue")),
            layout,
        )
        layout.addStretch()

    def build_about(self) -> None:
        layout = self.page("SCUF Automatic Mapping · 0.1.0")
        label = QLabel(
            "Local-first Windows companion for SCUF Envision Pro and iCUE 5+.\n\n"
            "No accounts, telemetry, drivers, input injection, or game memory inspection.\n"
            "Actual active iCUE profile is unknown. Hardware confirmations are user attestations.\n\n"
            "REQUIRES WINDOWS HARDWARE VALIDATION\n"
            "See docs/HARDWARE_ACCEPTANCE.md for repeatable acceptance tests.\n\n"
            "Independent project; not affiliated with or endorsed by SCUF or Corsair.\n"
            "License: all rights reserved, as selected by the repository owner."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()

    def refresh(self) -> None:
        self.worker.profiles = self.repo.profiles()
        self.worker.settings = self.settings
        self.refresh_table()
        selected = self.setup_choice.currentData()
        self.setup_choice.blockSignals(True)
        self.setup_choice.clear()
        for profile in self.worker.profiles:
            self.setup_choice.addItem(profile.game_name, profile.id)
        index = self.setup_choice.findData(selected)
        self.setup_choice.setCurrentIndex(max(0, index))
        self.setup_choice.blockSignals(False)
        self.load_attestations()
        self.refresh_events()

    def refresh_table(self) -> None:
        query = self.search.text().casefold()
        profiles = self.repo.profiles()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        missing = []
        for profile in profiles:
            if profile.executable_path and not Path(profile.executable_path).is_file():
                missing.append(f"Missing executable: {profile.game_name}")
            if (
                query
                not in " ".join(
                    (profile.game_name, profile.executable_name, profile.icue_profile_name)
                ).casefold()
            ):
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate(
                (
                    profile.game_name,
                    profile.executable_name,
                    profile.icue_profile_name,
                    profile.linked_app_attested_at or "Not configured",
                    profile.mapping_test_attested_at or "Not tested",
                    "Yes" if profile.enabled else "No",
                    profile.id,
                )
            ):
                item = QTableWidgetItem(value)
                item.setToolTip(profile.executable_path if col == 1 else value)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.conflicts.setText("\n".join(warnings(profiles) + missing))

    def selected(self, setup: bool = False) -> Profile | None:
        item = self.table.item(self.table.currentRow(), 6) if self.table.currentRow() >= 0 else None
        identity = self.setup_choice.currentData() if setup else (item.text() if item else None)
        return next((p for p in self.repo.profiles() if p.id == identity), None)

    def add_profile(self) -> None:
        self.edit_dialog(None)

    def edit_profile(self) -> None:
        if profile := self.selected():
            self.edit_dialog(profile)

    def edit_dialog(self, profile: Profile | None) -> None:
        dialog = ProfileDialog(self, profile, self.foreground)
        if dialog.exec() and dialog.result_profile:
            self.repo.save(dialog.result_profile)
            self.repo.event("Game mapping saved")
            self.refresh()

    def delete_profile(self) -> None:
        if (profile := self.selected()) and QMessageBox.question(
            self, "Delete game", f"Delete {profile.game_name}?"
        ) == QMessageBox.StandardButton.Yes:
            self.repo.delete(profile.id)
            self.repo.event("Game mapping deleted")
            self.refresh()

    def toggle_enabled(self) -> None:
        if profile := self.selected():
            profile.enabled = not profile.enabled
            profile.updated_at = now()
            self.repo.save(profile)
            self.refresh()

    def load_attestations(self) -> None:
        profile = self.selected(True)
        self.linked.setChecked(bool(profile and profile.linked_app_attested_at))
        self.tested.setChecked(bool(profile and profile.mapping_test_attested_at))
        self.setup_details.setText(
            f"Executable: {profile.executable_path or '(not yet selected)'}\n"
            f"Expected profile: {profile.icue_profile_name}\n{profile.state}\n"
            f"Linked: {profile.linked_app_attested_at or 'never'} · Tested: {profile.mapping_test_attested_at or 'never'}"
            if profile
            else "Add a game in Games to begin."
        )

    def attest(self) -> None:
        if profile := self.selected(True):
            if self.tested.isChecked() and not self.linked.isChecked():
                raise ValueError("Confirm the iCUE link before hardware testing")
            profile.linked_app_attested_at = (
                (profile.linked_app_attested_at or now()) if self.linked.isChecked() else None
            )
            profile.mapping_test_attested_at = (
                (profile.mapping_test_attested_at or now()) if self.tested.isChecked() else None
            )
            profile.updated_at = now()
            self.repo.save(profile)
            self.repo.event("User updated Linked App / hardware test attestation")
            self.refresh()

    def copy_field(self, field: str) -> None:
        if profile := self.selected(True):
            QApplication.clipboard().setText(getattr(profile, field))

    def open_folder(self) -> None:
        profile = self.selected(True)
        if not profile or not profile.executable_path:
            raise ValueError("Select an existing game executable first")
        path = Path(profile.executable_path)
        if not path.is_absolute() or not path.is_file() or path.suffix.casefold() != ".exe":
            raise ValueError("Game executable is missing or invalid")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def open_icue(self) -> None:
        path = Path(self.icue_path)
        # Only the documented iCUE application basename can be launched, even if the presence allowlist changes.
        if (
            not path.is_absolute()
            or not path.is_file()
            or path.name.casefold() not in {"icue.exe", "corsair.icue.exe"}
        ):
            raise ValueError("No accessible running iCUE executable found; open iCUE manually")
        if (
            QMessageBox.question(
                self, "Open detected iCUE", f"Open this detected executable?\n{path}"
            )
            == QMessageBox.StandardButton.Yes
        ):
            import subprocess

            subprocess.Popen([str(path)], shell=False)

    def refresh_events(self) -> None:
        self.events.setPlainText(
            "\n".join(
                f"{at}  {message}" for at, message in self.repo.events(self.event_search.text())
            )
        )

    def on_snapshot(self, snapshot: tuple) -> None:
        if self.exiting:
            return
        fg, result, changed, presence, path, stamp, paused = snapshot
        if paused != self.worker.paused:
            return  # Discard queued observations produced before pause/resume.
        self.foreground, self.icue_path = fg, path
        if not paused:
            self.last_observation = stamp
        profile = result.profile
        expected = profile.icue_profile_name if profile else "No game mapping"
        self.status.setText(
            f"Foreground: {fg.name or 'unknown'}\n{fg.path}\n"
            f"Matched game: {profile.game_name if profile else 'none'}\n"
            f"Expected iCUE profile: {expected}\n"
            f"Mapping state: {profile.state if profile else 'not configured'}\n"
            f"iCUE process: {presence} · Monitoring: {'paused' if paused else 'active'}\n"
            f"Last observation: {self.last_observation}\n{fg.error}\n"
            f"{'Conflicting rules — resolve in Games' if result.conflict else ''}\n"
            f"{('Unmatched reminder: ' + self.settings.default_profile) if not profile and self.settings.default_profile else ''}"
        )
        self.tray.setToolTip(f"Expected: {expected}"[:127])
        presence_changed = presence != self.presence
        if presence_changed:
            self.repo.event(f"iCUE process {presence}; activation unknown")
            self.presence = presence
        if changed:
            self.repo.event(
                f"Expected mapping: {expected}" + (" (conflict)" if result.conflict else "")
            )
            excluded = {n.strip().casefold() for n in self.settings.exclusions.split(",")}
            if (
                profile
                and self.settings.notifications
                and fg.name.casefold() not in excluded
                and profile.id != self.last_notified_id
                and time.monotonic() - self.last_notification >= 10
            ):
                self.tray.showMessage("Expected iCUE profile", expected)
                self.last_notification = time.monotonic()
                self.last_notified_id = profile.id
        if changed or presence_changed:
            self.refresh_events()

    def toggle_pause(self) -> None:
        self.worker.paused = not self.worker.paused
        self.pause_button.setText("Resume monitoring" if self.worker.paused else "Pause monitoring")
        self.repo.event("Monitoring paused" if self.worker.paused else "Monitoring resumed")

    def discover(self) -> None:
        self.worker.discover = True
        self.statusBar().showMessage("Reading running executable names and paths…", 4000)

    def show_discovery(self, processes: list) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Running processes — choose the actual game")
        dialog.resize(850, 500)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Filter processes")
        layout.addWidget(search)
        listing = QListWidget()
        layout.addWidget(listing)
        excluded = {n.strip().casefold() for n in self.settings.exclusions.split(",")}
        records = sorted({(p.name, p.path) for p in processes if p.name.casefold() not in excluded})

        def populate() -> None:
            listing.clear()
            listing.addItems(
                [
                    f"{name} | {path or '(path inaccessible)'}"
                    for name, path in records
                    if search.text().casefold() in f"{name} {path}".casefold()
                ]
            )

        search.textChanged.connect(populate)
        populate()

        def choose() -> None:
            if item := listing.currentItem():
                name, path = item.text().split(" | ", 1)
                self.foreground = Foreground(path if path != "(path inaccessible)" else "", name)
                dialog.accept()
                self.add_profile()

        button("Use selected process", choose, layout)
        dialog.exec()

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export profiles", "profiles.json", "JSON (*.json)"
        )
        if path:
            export_profiles(Path(path), self.repo.profiles())

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import profiles", "", "JSON (*.json)")
        if not path:
            return
        incoming = load_profiles(Path(path))
        existing = self.repo.profiles()
        box = QMessageBox(self)
        box.setWindowTitle("Import preview")
        box.setText(preview(incoming, existing))
        replace = box.addButton("Replace IDs", QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton("Skip existing IDs", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() not in (replace, skip):
            return
        ids = {p.id for p in existing}
        chosen = (
            incoming if box.clickedButton() == replace else [p for p in incoming if p.id not in ids]
        )
        self.repo.backup(self.repo.path.with_suffix(".pre-import.db"))
        self.repo.save_many(chosen)
        self.repo.event(f"Imported {len(chosen)} mappings; pre-import backup saved")
        self.refresh()

    def save_settings(self) -> None:
        values = asdict(self.settings)
        for name, widget in self.setting_widgets.items():
            if isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                values[name] = widget.value()
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text()
        settings = Settings(**values)
        if settings.autostart != self.settings.autostart:
            set_autostart(
                settings.autostart,
                WindowsRegistry(),
                Path(sys.executable),
                bool(getattr(sys, "frozen", False)),
            )
        try:
            self.repo.save_settings(settings)
        except Exception:
            if settings.autostart != self.settings.autostart:
                set_autostart(
                    self.settings.autostart,
                    WindowsRegistry(),
                    Path(sys.executable),
                    bool(getattr(sys, "frozen", False)),
                )
            raise
        self.settings = settings
        self.refresh()
        self.statusBar().showMessage("Settings saved", 4000)

    def backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Database backup", "scuf-backup.db", "SQLite (*.db)"
        )
        if path:
            self.repo.backup(Path(path))

    def diagnostics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostics", "diagnostics.txt", "Text (*.txt)"
        )
        if path:
            content = (
                f"SCUF Automatic Mapping 0.1.0\nPlatform: {sys.platform}\n{self.status.text()}\n"
            )
            content += "\n".join(f"{at} {message}" for at, message in self.repo.events())
            export_diagnostics(Path(path), content, self.raw_diagnostics.isChecked())

    def onboarding(self) -> None:
        QMessageBox.information(
            self,
            "Welcome — native iCUE setup",
            "Windows 10/11 and iCUE 5+ are required.\n"
            "Connect Envision Pro with the supplied SLIPSTREAM USB receiver, not Bluetooth.\n"
            "Add the actual game EXE in Games, then follow Setup to create and link a software profile in iCUE.\n"
            "iCUE switches mappings; this app shows expectations and your confirmations.\n"
            "No automatic download or installation occurs.",
        )
        self.settings.onboarding_complete = True
        self.repo.save_settings(self.settings)

    def restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def exit_app(self) -> None:
        self.exiting = True
        self.close()

    def shutdown(self) -> None:
        self.exiting = True
        self.worker.requestInterruption()
        self.worker.wait()
        self.tray.hide()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.exiting and self.settings.minimize_to_tray and self.tray.isVisible():
            self.hide()
            event.ignore()
            return
        self.shutdown()
        event.accept()
