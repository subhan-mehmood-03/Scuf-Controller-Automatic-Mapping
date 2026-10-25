from dataclasses import replace

import pytest
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from scuf_auto_mapping.domain.matcher import Match
from scuf_auto_mapping.domain.models import Foreground, Profile, now
from scuf_auto_mapping.infrastructure.repository_sqlite import Repository
from scuf_auto_mapping.infrastructure.import_export import load_profiles
from scuf_auto_mapping.ui.window import ProfileDialog, Window


def test_library_setup_navigation(qtbot, tmp_path, monkeypatch):
    repo = Repository(tmp_path / "test.db")
    window = Window(repo, start_worker=False)
    qtbot.addWidget(window)
    window.show()
    for index in range(6):
        window.nav.setCurrentRow(index)
        assert window.pages.currentIndex() == index
    profile = Profile("Game", "game.exe", "Competitive")
    repo.save(profile)
    window.refresh()
    assert window.table.rowCount() == 1
    window.search.setText("no match")
    assert window.table.rowCount() == 0
    window.search.clear()
    window.table.selectRow(0)
    window.toggle_enabled()
    assert not repo.profiles()[0].enabled
    window.linked.setChecked(True)
    window.tested.setChecked(True)
    window.attest()
    assert repo.profiles()[0].mapping_test_attested_at
    window.on_snapshot(
        (Foreground(name="game.exe"), Match(profile), True, "detected", "", now(), False)
    )
    assert "Expected iCUE profile: Competitive" in window.status.text()
    window.toggle_pause()
    assert window.worker.paused
    window.on_snapshot((Foreground(), Match(), True, "unknown", "", now(), False))
    assert "Competitive" in window.status.text()  # stale snapshot discarded
    window.toggle_pause()
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    window.table.selectRow(0)
    window.delete_profile()
    assert not repo.profiles()
    window.close()
    repo.close()


def test_profile_dialog_validation_and_reset(qtbot):
    dialog = ProfileDialog(None)
    qtbot.addWidget(dialog)
    dialog.save()
    assert dialog.error.text()
    dialog.fields["game_name"].setText("Game")
    dialog.fields["icue_profile_name"].setText("Profile")
    dialog.use_path(r"C:\Games\game.exe")
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    profile = replace(
        dialog.result_profile, linked_app_attested_at=now(), mapping_test_attested_at=now()
    )
    edit = ProfileDialog(None, profile)
    qtbot.addWidget(edit)
    edit.fields["icue_profile_name"].setText("Changed")
    edit.save()
    assert edit.result_profile.linked_app_attested_at is None


def test_settings_exports_and_failed_paths(qtbot, tmp_path, monkeypatch):
    repo = Repository(tmp_path / "test.db")
    repo.save(Profile("Game", "game.exe", "Expected"))
    window = Window(repo, start_worker=False)
    qtbot.addWidget(window)
    window.setting_widgets["interval_ms"].setValue(500)
    window.setting_widgets["notifications"].setChecked(True)
    window.save_settings()
    assert repo.settings().interval_ms == 500
    assert repo.settings().notifications
    target = tmp_path / "export.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(target), ""))
    window.export_json()
    assert load_profiles(target)[0].game_name == "Game"
    with pytest.raises(ValueError, match="existing"):
        window.open_folder()
    with pytest.raises(ValueError, match="iCUE"):
        window.open_icue()
    window.linked.setChecked(False)
    window.tested.setChecked(True)
    with pytest.raises(ValueError, match="Confirm"):
        window.attest()
    window.copy_field("icue_profile_name")
    from PySide6.QtWidgets import QApplication

    assert QApplication.clipboard().text() == "Expected"
    window.close()
    repo.close()


def test_notification_dedup_and_stale_shutdown(qtbot, tmp_path, monkeypatch):
    repo = Repository(tmp_path / "test.db")
    window = Window(repo, start_worker=False)
    qtbot.addWidget(window)
    window.settings.notifications = True
    profile = Profile("Game", "game.exe", "Expected")
    messages = []
    monkeypatch.setattr(window.tray, "showMessage", lambda *args: messages.append(args))
    frame = (Foreground(name="game.exe"), Match(profile), True, "detected", "", now(), False)
    window.on_snapshot(frame)
    assert len(messages) == 1
    window.last_notification = 0
    window.on_snapshot(frame)
    assert len(messages) == 1
    window.on_snapshot(
        (Foreground(name="explorer.exe"), Match(), True, "detected", "", now(), False)
    )
    assert len(messages) == 1
    before = window.status.text()
    window.shutdown()
    window.on_snapshot(frame)
    assert window.status.text() == before
    window.close()
    repo.close()
