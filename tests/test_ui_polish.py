"""Offline interaction checks for pairing recovery and playback overflow."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PyQt6.QtCore import QSettings, pyqtSignal, Qt, QEvent, QPointF
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget, QComboBox, QStyle, QStyleOptionComboBox
import luma
from backend import Client, Vault
from player_view import PlaybackView, RoundedMenu

APP = QApplication.instance() or QApplication([])
APP.setStyle('Fusion')
APP.setStyleSheet(luma.STYLE)

class Surface(QWidget):
    failure = pyqtSignal(str)
    def __init__(self, player, parent=None):
        super().__init__(parent)

class PolishTests(unittest.TestCase):
    def test_control_panel_clicks_do_not_toggle_playback(self):
        player = self.window.player
        with patch.object(player, 'pause') as pause, patch('player_view.VideoSurface', Surface):
            view = PlaybackView(player, 'Click routing fixture', *[Mock() for _ in range(6)])
            view.resize(1280, 800)
            view.show()
            APP.processEvents()

            def click(widget, point=None):
                point = point or widget.rect().center()
                for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                    event = QMouseEvent(kind, QPointF(point), QPointF(widget.mapToGlobal(point)), Qt.MouseButton.LeftButton,
                                       Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton,
                                       Qt.KeyboardModifier.NoModifier)
                    APP.sendEvent(widget, event)
                APP.processEvents()

            try:
                for widget in (view.top, view.bottom, view.title, view.position, view.source, view.total, view.seek):
                    click(widget)
                    pause.assert_not_called()
                click(view.play_button)
                pause.assert_called_once()
                pause.reset_mock()
                click(view.overlay)
                pause.assert_called_once()
                pause.reset_mock()
                view.set_mini(True)
                view.click_timer.setInterval(1)
                for widget in (view.mini_top, view.mini_bottom, view.mini_title):
                    click(widget)
                    self.assertFalse(view.click_timer.isActive(), 'Panel clicks must not schedule a delayed pause')
                click(view.mini_pause)
                pause.assert_called_once()
                pause.reset_mock()
                click(view.mini_overlay)
                time.sleep(.01)
                APP.processEvents()
                pause.assert_called_once()
            finally:
                view.close()

    def test_dropdown_arrow_has_space_at_right_edge(self):
        combo = QComboBox()
        combo.addItem('English subtitles')
        combo.resize(260, 42)
        combo.show()
        try:
            APP.processEvents()
            option = QStyleOptionComboBox()
            combo.initStyleOption(option)
            arrow = combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, combo)
            self.assertGreater(arrow.center().x(), combo.width() - 55)
            self.assertLess(arrow.right(), combo.width())
            self.assertGreaterEqual(arrow.top(), 0)
            self.assertLess(arrow.bottom(), combo.height())
            image = combo.grab().toImage()
            chevron = [(x, y) for x in range(arrow.left(), arrow.right() + 1) for y in range(arrow.top(), arrow.bottom() + 1) if image.pixelColor(x, y).red() > 160 and image.pixelColor(x, y).green() > 180]
            self.assertGreater(len(chevron), 10, 'Right arrow must actually render')
        finally:
            combo.close()

    def test_popup_window_corners_follow_rounded_outline(self):
        menu = RoundedMenu()
        menu.addAction('Choose source')
        menu.addAction('Sleep timer')
        menu.show()
        try:
            APP.processEvents()
            self.assertFalse(menu.mask().contains(menu.rect().topLeft()))
            self.assertTrue(menu.mask().contains(menu.rect().center()))
            self.assertEqual(menu.grab().toImage().pixelColor(0, 0).alpha(), 0)
            menu.resize(menu.width() + 80, menu.height() + 20)
            APP.processEvents()
            self.assertFalse(menu.mask().contains(menu.rect().bottomRight()))
            self.assertTrue(menu.mask().contains(menu.rect().center()))
        finally:
            menu.close()

    def test_update_check_private_token_retry_and_current_release(self):
        from PyQt6.QtWidgets import QPushButton,QLineEdit,QLabel
        import updater
        pending=[]
        self.window.work=lambda task,done,failed,**kwargs:pending.append((task,done,failed,kwargs))
        self.window.check_updates()
        dialog=self.window._update_dialog
        self.assertEqual(pending[-1][3]['token'],-1)
        pending[-1][2](updater.AuthenticationRequired('Private repository needs a token.'))
        field=dialog.findChild(QLineEdit)
        self.assertFalse(field.isHidden())
        self.assertEqual(field.echoMode(),QLineEdit.EchoMode.Password)
        action=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Check with token')
        field.setText('test-only-token');action.click()
        self.assertEqual(len(pending),2)
        pending[-1][1](None)
        self.assertTrue(any('up to date' in label.text() for label in dialog.findChildren(QLabel)))
        dialog.close()
        self.assertIsNone(self.window._update_dialog)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.work = patch.object(luma.Window, 'work', lambda *a, **k: None)
        self.work.start()
        with patch.object(luma, 'Client', side_effect=lambda: Client(Vault(Path(self.folder.name) / 'unused.enc'))), patch.object(luma, 'QSettings', side_effect=lambda *a: QSettings(str(Path(self.folder.name) / 'settings.ini'), QSettings.Format.IniFormat)):
            self.window = luma.Window(preview=True)

    def tearDown(self):
        self.window.close()
        self.window.client.pool.shutdown(wait=True, cancel_futures=True)
        self.work.stop()
        APP.processEvents()
        self.folder.cleanup()

    def test_pairing_failure_retry_expiry_and_stale_response(self):
        self.window.pair()
        pending = []
        self.window.work = lambda f, done, failed: pending.append((done, failed))
        self.window.new_code()
        self.assertFalse(self.window.new_code_button.isEnabled())
        pending[-1][1](OSError('offline'))
        self.assertTrue(self.window.new_code_button.isEnabled())
        self.assertIn('unavailable', self.window.qr.text())
        self.window.new_code()
        old = pending[-1]
        self.window.new_code()
        old[0]({'code': 'stale'})
        old[1](OSError())
        self.assertFalse(self.window.new_code_button.isEnabled())
        self.assertEqual(self.window.pair_code, '')
        pending[-1][0]({'code': 'fixture'})
        self.assertTrue(self.window.new_code_button.isEnabled())
        self.window.pair_started = time.monotonic() - 601
        self.window.poll_pair()
        self.assertEqual(self.window.pair_code, '')
        self.assertEqual(self.window.qr.text(), 'Code expired')
        self.assertFalse(self.window.pair_timer.isActive())

    def test_overflow_callbacks_and_controls_fit_small_window(self):
        callbacks = [Mock() for _ in range(6)]
        with patch('player_view.VideoSurface', Surface):
            view = PlaybackView(self.window.player, 'Offline fixture', *callbacks)
        try:
            view.resize(980, 700)
            view.show()
            APP.processEvents()
            for action, callback in zip(view.more_menu.actions(), (callbacks[2], callbacks[3], callbacks[4])):
                action.trigger()
                callback.assert_called_once()
            self.assertLessEqual(view.minimumSizeHint().width(), 980)
            self.assertEqual(view.play_button.height(), 36)
            with patch.object(QApplication, 'activePopupWidget', return_value=view.more_menu):
                view.hide_controls()
                self.assertTrue(view.visible_controls)
        finally:
            view.close()

if __name__ == '__main__':
    unittest.main()
