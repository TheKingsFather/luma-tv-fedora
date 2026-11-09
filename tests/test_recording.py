"""Real recording files and isolated UI checks; no account or network access."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import time
import threading
import unittest
from concurrent.futures import Future
from unittest.mock import patch
from PyQt6.QtCore import QSettings,QTimer,Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QWidget,QLineEdit
from player import Player
from backend import Client,Vault
import luma

APP=QApplication.instance() or QApplication([])
APP.setStyle('Fusion');APP.setStyleSheet(luma.STYLE)


class RecordingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='luma-recording-tests-')
        cls.clip=Path(cls.folder.name)/'source.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
                        '-f','lavfi','-i','sine=frequency=330:sample_rate=48000','-t','12','-c:v','libx264',
                        '-preset','ultrafast','-g','24','-c:a','aac',str(cls.clip)],check=True)

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def setUp(self):
        self.output=tempfile.TemporaryDirectory(prefix='luma-recording-output-')
        self.player=Player();self.player.headless=True;self.saved=[];self.errors=[]
        self.player.recording_saved.connect(self.saved.append);self.player.recording_error.connect(self.errors.append)

    def tearDown(self):
        self.player.shutdown();APP.processEvents();self.output.cleanup()

    def wait(self,predicate,seconds=8):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:APP.processEvents();time.sleep(.02)
        self.assertTrue(predicate(),'Timed out waiting for recording/playback state')

    def play(self):
        self.player.start([{'url':self.clip.as_uri(),'name':'Generated fixture'}])
        self.wait(lambda:self.player.media_loaded and self.player.position>.3)

    def target(self,name='recording.mkv'):return Path(self.output.name)/name

    def assert_valid(self,path):
        result=subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(path)],text=True)
        kinds={stream['codec_type'] for stream in json.loads(result)['streams']}
        self.assertEqual(kinds,{'video','audio'})
        subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True)

    def record(self,path):
        with patch('subprocess.Popen',side_effect=AssertionError('Recording must stay inside libmpv')):
            self.assertTrue(self.player.start_recording(path))
        self.wait(lambda:path.exists() and path.stat().st_size>1024)

    def test_start_stop_writes_playable_audio_video_without_replacing_engine(self):
        self.play();engine=self.player.engine;path=self.target();self.record(path)
        self.player.stop_recording();APP.processEvents()
        self.assertFalse(self.player.recording);self.assertIs(self.player.engine,engine)
        self.assertEqual(self.saved,[str(path)]);self.assertFalse(self.errors)
        self.assert_valid(path)
        before=self.player.position;self.wait(lambda:self.player.position>before+.2)
        self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_seek_finishes_recording_and_a_second_recording_can_start(self):
        self.play();first=self.target();self.record(first)
        self.player.seek(3);self.assertFalse(self.player.recording)
        self.wait(lambda:self.player.position>=2.8)
        second=self.target('second.mkv');self.record(second);self.player.stop()
        APP.processEvents();self.assertEqual(self.saved,[str(first),str(second)])
        self.assert_valid(first);self.assert_valid(second)

    def test_switching_source_and_shutdown_each_finalize_the_file(self):
        self.play();first=self.target();self.record(first)
        self.player.start([{'url':self.clip.as_uri(),'name':'Another source'}])
        self.assertFalse(self.player.recording)
        self.wait(lambda:self.player.media_loaded and self.player.position>.3)
        second=self.target('shutdown.mkv');self.record(second);self.player.shutdown()
        APP.processEvents();self.assertEqual(self.saved,[str(first),str(second)])
        self.assert_valid(first);self.assert_valid(second)

    def test_existing_files_bad_destinations_and_idle_player_are_preserved(self):
        self.assertFalse(self.player.start_recording(self.target()))
        self.play();path=self.target();path.write_bytes(b'keep this original')
        self.assertFalse(self.player.start_recording(path));self.assertEqual(path.read_bytes(),b'keep this original')
        self.assertFalse(self.player.start_recording(self.target('missing')/'clip.mkv'))
        self.assertFalse(self.player.start_recording(self.target('clip.mp4')))
        self.assertFalse(self.player.recording)

    def test_async_recording_failure_cleans_empty_file_and_resets_state(self):
        self.play();future=Future();path=self.target()
        with patch.object(self.player.engine,'command_async',return_value=future):
            self.assertTrue(self.player.start_recording(path))
        future.set_exception(RuntimeError('Unsupported muxer fixture'));APP.processEvents()
        self.assertFalse(self.player.recording);self.assertFalse(path.exists());self.assertTrue(self.errors)

    def test_native_stop_error_keeps_recording_and_playback_alive(self):
        self.play();path=self.target();self.record(path)
        command=self.player.engine.command
        def close_with_error(*args):
            result=command(*args)
            if args[0]=='dump-cache':raise SystemError('mpv command failed',-12)
            return result
        with patch.object(self.player.engine,'command',side_effect=close_with_error):
            self.player.stop_recording()
        self.assertFalse(self.player.recording);self.assertEqual(self.saved,[str(path)])
        self.assertTrue(self.errors);self.assert_valid(path)
        before=self.player.position;self.wait(lambda:self.player.position>before+.2)

    def test_end_of_playback_finalizes_recording_once(self):
        self.play();self.player.seek(10);self.wait(lambda:self.player.position>=9.8)
        path=self.target();self.record(path)
        self.wait(lambda:bool(self.saved),seconds=5)
        self.assertFalse(self.player.recording);self.assertEqual(self.saved,[str(path)])
        self.assert_valid(path)

    def test_authenticated_http_transport_stream_records_without_an_extra_connection(self):
        ts=self.target('source.ts')
        subprocess.run(['ffmpeg','-v','error','-i',str(self.clip),'-c','copy','-f','mpegts',str(ts)],check=True)
        data=ts.read_bytes();requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                requests.append(self.headers.get('X-Luma-Test'))
                if self.headers.get('X-Luma-Test')!='fixture-only':
                    self.send_error(403);return
                self.send_response(200);self.send_header('Content-Type','video/mp2t');self.end_headers()
                try:
                    for offset in range(0,len(data),1316):
                        self.wfile.write(data[offset:offset+1316]);self.wfile.flush();time.sleep(.003)
                except (BrokenPipeError,ConnectionResetError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            self.player.start([{'url':'http://127.0.0.1:'+str(server.server_port)+'/live.ts',
                                'behaviorHints':{'proxyHeaders':{'request':{'X-Luma-Test':'fixture-only'}}}}])
            self.wait(lambda:self.player.media_loaded and self.player.position>.3)
            before=len(requests);path=self.target();self.record(path);self.player.stop_recording()
            self.assertEqual(len(requests),before);self.assertEqual(set(requests),{'fixture-only'})
            self.assert_valid(path)
        finally:
            self.player.stop();server.shutdown();server.server_close();thread.join(timeout=3)


class RecordingUiTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix='luma-recording-ui-')
        with patch.object(luma.Window,'work',lambda *args,**kwargs:None), \
             patch.object(luma,'Client',side_effect=lambda:Client(vault=Vault(Path(self.folder.name)/'unused.enc'))):
            self.window=luma.Window(preview=True)
        self.window.settings=QSettings(str(Path(self.folder.name)/'settings.ini'),QSettings.Format.IniFormat)
        self.window.settings.setValue('recordingDirectory',self.folder.name)
        self.window.play_title={'name':'Fixture channel / a title'};self.window.player.media_loaded=True
        # UI behavior independent of OpenGL: actual media is checked above.
        class Surface(QWidget):
            from PyQt6.QtCore import pyqtSignal
            failure=pyqtSignal(str)
            def __init__(self,player,parent=None):super().__init__(parent)
        with patch('player_view.VideoSurface',Surface):self.window.now_playing()
        self.view=self.window.playback_view

    def tearDown(self):
        self.window.player.recording_path=None
        self.window.close();self.window.client.pool.shutdown(wait=True,cancel_futures=True)
        APP.processEvents();self.folder.cleanup()

    def test_save_dialog_cancel_and_success_remembers_folder(self):
        self.window.show()
        with patch.object(self.window.player,'start_recording') as start:
            QTest.mouseClick(self.view.record_button,Qt.MouseButton.LeftButton)
            dialog=self.window._record_dialog
            self.assertTrue(dialog.isVisible())
            # The click returns with the picker still open, and Qt timers run.
            ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(10)
            QTest.qWait(100);timer.stop();self.assertGreater(len(ticks),1)
            self.window.toggle_recording();self.assertIs(self.window._record_dialog,dialog)
            dialog.reject();self.assertIsNone(self.window._record_dialog)
            start.assert_not_called()
        target=Path(self.folder.name)/'my clip.mkv'
        with patch.object(self.window.player,'start_recording',return_value=True) as start:
            self.window.toggle_recording();dialog=self.window._record_dialog
            dialog.findChild(QLineEdit,'fileNameEdit').setText(str(target));dialog.accept();start.assert_called_once_with(target)
        self.assertIsNone(self.window._record_dialog)
        self.assertEqual(self.window.settings.value('recordingDirectory'),self.folder.name)

    def test_active_indicator_persists_when_controls_hide_and_in_mini_mode(self):
        self.window.show();self.window.player.recording_path=Path(self.folder.name)/'recording.mkv'
        self.window.player.recording_started=time.monotonic()-65
        self.view.update_recording();self.assertIn('1:05',self.view.record_button.text())
        color=self.view.record_button.grab().toImage().pixelColor(12,self.view.record_button.height()//2)
        self.assertGreater(color.red(),color.green()*2,'Active recording must have a red button')
        self.view.hide_controls();self.assertFalse(self.view.record_badge.isHidden())
        self.view.set_mini(True);self.view.hide_controls();self.assertFalse(self.view.record_badge.isHidden())
        self.view.show_controls();self.assertTrue(self.view.record_badge.isHidden())
        self.assertFalse(self.view.mini_record.isHidden())
        self.window.player.recording_path=None;self.view.update_recording()
        self.assertTrue(self.view.record_badge.isHidden());self.assertTrue(self.view.mini_record.isHidden())
        color=self.view.record_button.grab().toImage().pixelColor(12,self.view.record_button.height()//2)
        self.assertLess(color.red(),color.green(),'Idle recording must return to the glass style')

    def test_source_change_while_choosing_a_filename_does_not_record_the_wrong_title(self):
        with patch.object(self.window.player,'start_recording') as start:
            self.window.toggle_recording();dialog=self.window._record_dialog
            self.window.player.streams=[{'url':'https://fixture.invalid/another-source'}]
            dialog.findChild(QLineEdit,'fileNameEdit').setText(str(Path(self.folder.name)/'clip.mkv'));dialog.accept()
            start.assert_not_called()
        self.assertIn('source changed',self.view.record_notice_text.text())

    def test_record_button_picker_and_real_recording_keep_playback_responsive(self):
        clip=Path(self.folder.name)/'source.mp4';target=Path(self.folder.name)/'clip.mkv'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
                        '-f','lavfi','-i','sine=frequency=330:sample_rate=48000','-t','8',
                        '-c:v','libx264','-preset','ultrafast','-g','24','-c:a','aac',str(clip)],check=True)
        player=self.window.player;player.headless=True
        player.start([{'url':clip.as_uri(),'name':'Recording dialog fixture'}])
        def wait(predicate):
            deadline=time.monotonic()+5
            while not predicate() and time.monotonic()<deadline:QTest.qWait(20)
            self.assertTrue(predicate(),'Recording UI or playback stopped responding')
        try:
            wait(lambda:player.media_loaded and player.position>.2)
            self.window.show();QTest.mouseClick(self.view.record_button,Qt.MouseButton.LeftButton)
            dialog=self.window._record_dialog;self.assertTrue(dialog.isVisible())
            before=player.position;wait(lambda:player.position>before+.3)
            dialog.findChild(QLineEdit,'fileNameEdit').setText(str(target));dialog.accept()
            self.assertTrue(player.recording);self.assertIn('Stop',self.view.record_button.text())
            wait(lambda:target.exists() and target.stat().st_size>1024)
            before=player.position;wait(lambda:player.position>before+.3)
            QTest.mouseClick(self.view.record_button,Qt.MouseButton.LeftButton)
            self.assertFalse(player.recording);self.assertIn('Record',self.view.record_button.text())
            before=player.position;wait(lambda:player.position>before+.2)
            subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','null','-'],check=True,capture_output=True)
        finally:player.stop()

    def test_closing_window_cancels_pending_recording(self):
        with patch.object(self.window.player,'start_recording') as start:
            self.window.toggle_recording();dialog=self.window._record_dialog
            self.window.close();self.assertIsNone(self.window._record_dialog)
            self.assertFalse(dialog.isVisible());start.assert_not_called()

    def test_save_window_belongs_to_the_visible_mini_player(self):
        self.window.show()
        with patch.object(self.window,'home',lambda *args:None):self.window.enter_mini_player()
        self.window.toggle_recording();dialog=self.window._record_dialog
        self.assertIs(dialog.parent(),self.window.mini_window)
        self.assertTrue(dialog.isVisible());self.assertTrue(dialog.isModal())
        dialog.reject();self.assertIsNone(self.window._record_dialog)
        self.window.restore_player()

    def test_saved_notice_has_a_folder_action_and_shortcut_is_local(self):
        self.view.recording_saved(str(Path(self.folder.name)/'clip.mkv'))
        self.assertIn('Saved to',self.view.record_notice_text.text())
        self.assertFalse(self.view.open_recording_folder.isHidden())
        from PyQt6.QtCore import Qt
        self.assertEqual(self.view.record_shortcut.context(),Qt.ShortcutContext.WidgetWithChildrenShortcut)
