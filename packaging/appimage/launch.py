"""Packaged entry point, with offline checks that use temporary account settings."""
import ctypes.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent


def prepare_runtime():
    """Resolve libmpv without depending on host ldconfig or development tools."""
    native_find = ctypes.util.find_library
    bundled_mpv = Path(os.environ['APPDIR']) / 'usr/lib/libmpv.so.2'
    ctypes.util.find_library = lambda name: str(bundled_mpv) if name == 'mpv' else native_find(name)
    try:
        import mpv
    finally:
        ctypes.util.find_library = native_find
    # Fedora patches both certifi and Requests to use an absolute host path.
    # Keep their public helpers and adapter defaults on the bundled CA roots.
    import certifi
    import certifi.core
    certifi.where = certifi.core.where = lambda: str(ROOT / 'cacert.pem')
    import requests
    requests.certs.where = certifi.where
    requests.utils.DEFAULT_CA_BUNDLE_PATH = certifi.where()
    requests.adapters.DEFAULT_CA_BUNDLE_PATH = certifi.where()


def self_test(render=False):
    from unittest.mock import patch
    from cryptography.fernet import Fernet
    from PyQt6.QtCore import QSettings, Qt, QPoint, QPointF, QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication,QLineEdit
    import luma
    from backend import Client, Vault

    def wait_for(app, predicate, description, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(0.025)
        raise RuntimeError(description + ' timed out')

    with tempfile.TemporaryDirectory(prefix='luma-appimage-test-') as directory:
        temporary = Path(directory)
        for settings_format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
            for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope):
                QSettings.setPath(settings_format, scope, str(temporary / 'preferences'))
        vault = Vault(temporary / 'session.enc')
        vault.cipher = Fernet(Fernet.generate_key())
        vault.save({'key': 'offline-packaging-fixture'})
        assert vault.load()['key'] == 'offline-packaging-fixture'
        assert b'offline-packaging-fixture' not in vault.path.read_bytes()

        app = QApplication([sys.argv[0]])
        app.setStyle('Fusion')
        app.setStyleSheet(luma.STYLE)
        # No account, pairing, provider or artwork requests are made by this check.
        with patch.object(luma.Window, 'work', lambda *args, **kwargs: None), \
                patch.object(luma, 'Client', side_effect=lambda: Client(vault=Vault(temporary / 'unused.enc'))):
            window = luma.Window(preview=True)
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if render:
            window.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                                  Qt.WindowType.BypassWindowManagerHint |
                                  Qt.WindowType.WindowDoesNotAcceptFocus)
            # Xvfb is an isolated display. Keep the fixture on-screen so Qt
            # and Mesa actually composite the OpenGL widget.
            window.move(0, 0)
        window.resize(1280, 800)
        try:
            with patch.object(window, 'work', lambda *args, **kwargs: None):
                window.pair()
                window.pair_status.setText('Offline package verification')
                window.show()
                app.processEvents()
                assert window.windowTitle() == 'Luma TV'
                assert (ROOT / 'chevron.svg').is_file()
                assert not window.windowIcon().isNull()
                assert str(temporary) in window.settings.fileName()
                assert not window.client.connected
                for argument in sys.argv[1:]:
                    if argument.startswith('--self-test-screenshot='):
                        assert window.grab().save(argument.split('=', 1)[1])

                clip = ROOT / 'playback-test.mp4'
                assert clip.is_file()
                window.player.headless = not render
                if render:
                    # Keep the native renderer, while avoiding real speaker output.
                    import mpv
                    native_engine = mpv.MPV

                    def test_engine(*args, **options):
                        return native_engine(*args, **dict(options, ao='null', hwdec='no'))

                    with patch('player.mpv.MPV', side_effect=test_engine):
                        window.play({'id': 'fixture', 'name': 'Local playback check', 'type': 'movie'},
                                    'fixture', [{'url': clip.as_uri(), 'name': 'H.264 / AAC'}])
                else:
                    window.player.start([{'url': clip.as_uri(), 'name': 'H.264 / AAC'}])

                wait_for(app, lambda: window.player.position > .3 and not window.player.loading,
                         'Bundled libmpv video/audio playback')
                wait_for(app, lambda: bool(window.player.quality), 'Current decoded stream resolution')
                params=window.player.engine.video_params
                assert window.player.quality == f"{params['h']}p"
                if render:
                    assert window.playback_view.quality.text() == window.player.quality
                    assert window.playback_view.mini_quality.text() == window.player.quality
                assert window.player.engine.video_dec_params
                assert any(track.get('type') == 'audio' for track in window.player.tracks)
                if render:
                    def frame_decoded():
                        surface = window.playback_view.video
                        image = surface.grabFramebuffer()
                        if image.isNull() or surface.frames < 2:
                            return False
                        colors = {image.pixelColor(int(image.width() * x), int(image.height() * y)).rgb()
                                  for x in (.2, .4, .6, .8) for y in (.25, .5, .75)}
                        return len(colors) > 5

                    try:
                        wait_for(app, frame_decoded, 'Embedded OpenGL framebuffer')
                    except RuntimeError:
                        surface=window.playback_view.video;image=surface.grabFramebuffer()
                        print(json.dumps({'render_diagnostics':{'frames':surface.frames,'width':image.width(),'height':image.height(),'position':window.player.position,'visible':surface.isVisible()}}),flush=True)
                        for argument in sys.argv[1:]:
                            if argument.startswith('--self-test-player-screenshot='):
                                window.grab().save(argument.split('=',1)[1])
                        raise
                # Establish rendered frames while playback is advancing; pausing
                # immediately after an asynchronous seek can freeze a blank FBO.
                window.player.pause()
                window.player.seek(3)
                wait_for(app, lambda: window.player.paused and window.player.position > 2.8,
                         'Pause and seek')
                if render:
                    # Check native Qt event propagation after establishing the
                    # framebuffer, without changing the fixture's playback clock.
                    view = window.playback_view
                    with patch.object(window.player, 'pause') as unintended_pause:
                        for panel in (view.top, view.bottom, view.position, view.source):
                            point = panel.rect().topLeft() + QPoint(2, 2)
                            for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                                event = QMouseEvent(kind, QPointF(point), QPointF(panel.mapToGlobal(point)), Qt.MouseButton.LeftButton,
                                                   Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton,
                                                   Qt.KeyboardModifier.NoModifier)
                                app.sendEvent(panel, event)
                            app.processEvents()
                            unintended_pause.assert_not_called()
                    for argument in sys.argv[1:]:
                        if argument.startswith('--self-test-player-screenshot='):
                            assert window.grab().save(argument.split('=', 1)[1])
                    menu = window.playback_view.more_menu
                    menu.popup(window.playback_view.more_button.mapToGlobal(QPoint(0, 0)))
                    app.processEvents()
                    assert menu.isVisible()
                    assert not menu.mask().contains(menu.rect().topLeft())
                    assert menu.grab().toImage().pixelColor(0, 0).alpha() == 0
                    for argument in sys.argv[1:]:
                        if argument.startswith('--self-test-menu-screenshot='):
                            assert menu.grab().save(argument.split('=', 1)[1])
                    menu.close()
                    app.processEvents()
                    engine = window.player.engine
                    window.toggle_mini_player()
                    app.processEvents()
                    assert window.mini_mode and window.mini_window.isVisible()
                    assert window.player.engine is engine
                    window.restore_player()
                    app.processEvents()
                    assert not window.mini_mode and window.player.engine is engine
                # Exercise the actual save dialog and recorder in the bundled
                # Python/Qt/libmpv runtime, with no account or external stream.
                window.play_title = {'id': 'fixture', 'name': 'Recording check', 'type': 'movie'}
                window.settings.setValue('recordingDirectory', str(temporary))
                window.player.pause()
                wait_for(app, lambda: not window.player.paused, 'Resume before recording')
                window.toggle_recording()
                dialog = window._record_dialog
                assert dialog is not None and dialog.isVisible()
                if render:
                    dialog.move(-5000, -5000)
                before = window.player.position
                wait_for(app, lambda: window.player.position > before + .2,
                         'Playback with save window open')
                recording = temporary / 'recording.mkv'
                dialog.findChild(QLineEdit, 'fileNameEdit').setText(str(recording))
                dialog.accept()
                assert window.player.recording
                before = window.player.position
                wait_for(app, lambda: recording.stat().st_size > 0 and window.player.position > before + .2,
                         'Recording while playback continues')
                window.player.stop_recording()
                assert not window.player.recording and recording.stat().st_size > 0
                window.player.start([{'url': recording.as_uri(), 'name': 'Recorded fixture'}])
                wait_for(app, lambda: window.player.media_loaded and window.player.position > .1,
                         'Recorded video playback')
                wait_for(app, lambda: bool(window.player.quality), 'Current decoded stream resolution')
                params=window.player.engine.video_params
                assert window.player.quality == f"{params['h']}p"
                if render:
                    assert window.playback_view.quality.text() == window.player.quality
                    assert window.playback_view.mini_quality.text() == window.player.quality
                assert window.player.engine.video_dec_params
                assert any(track.get('type') == 'audio' for track in window.player.tracks)
        finally:
            window.close()
            app.processEvents()
            window.client.pool.shutdown(wait=True, cancel_futures=True)
            luma.POOL.shutdown(wait=True, cancel_futures=True)
            luma.IMAGES.shutdown(wait=True, cancel_futures=True)
            luma.WRITES.shutdown(wait=True, cancel_futures=True)
        assert window.player.engine is None
        import requests
        assert Path(requests.certs.where()).is_file()
        import ssl
        assert ssl.create_default_context(cafile=requests.certs.where()).cert_store_stats()['x509_ca'] > 100
        from types import SimpleNamespace
        connection = SimpleNamespace()
        requests.adapters.HTTPAdapter().cert_verify(connection, 'https://example.org', True, None)
        assert connection.ca_certs == str(ROOT / 'cacert.pem')
        print(json.dumps({'result': 'passed', 'app': 'Luma TV', 'version': luma.VERSION,
                          'python': sys.version.split()[0],
                          'checks': ['GUI startup', 'bundled libmpv H.264/AAC decode',
                                     'pause and seek', 'encrypted temporary vault',
                                     'CA certificates', 'isolated preferences', 'nonblocking recording dialog',
                                     'recording start/stop and recorded video/audio playback'] +
                                    (['embedded OpenGL frames', 'mini player', 'control panel click routing'] if render else [])}),
              flush=True)
    return 0


def main():
    os.umask(0o077)
    prepare_runtime()
    if '--self-test' in sys.argv or '--self-test-render' in sys.argv:
        return self_test(render='--self-test-render' in sys.argv)
    import luma
    return luma.main()


if __name__ == '__main__':
    sys.exit(main())
