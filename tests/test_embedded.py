"""Real GL video tests; run in a separate xcb test process, off the visible desktop."""
import os
import time
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path
from PyQt6.QtWidgets import QApplication,QLineEdit
from PyQt6.QtCore import Qt,QSettings
from PyQt6.QtTest import QTest
from luma import Window,STYLE
from cards import MediaCard
from player_view import MiniPlayer

APP=QApplication.instance() or QApplication([])
APP.setStyle('Fusion');APP.setStyleSheet(STYLE)

@unittest.skipUnless(os.environ.get('QT_QPA_PLATFORM')=='xcb','Real OpenGL requires the isolated xcb test run')
class EmbeddedTests(unittest.TestCase):
    def setUp(self):
        # Catalog requests are unrelated to rendering and can race a test's
        # playback navigation. Keep this suite entirely on local fixtures.
        for name,replacement in [('refresh',{'return_value':None}),('refresh_addons',{'return_value':None}),
                                 ('catalog',{'return_value':[]}),('meta',{'side_effect':lambda title:title})]:
            mocked=patch('backend.Client.'+name,**replacement)
            mocked.start();self.addCleanup(mocked.stop)
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='luma-render-test-')
        cls.clip=Path(cls.folder.name)/'test.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24','-f','lavfi','-i','sine=frequency=330:sample_rate=48000','-t','18','-c:v','libx264','-preset','ultrafast','-c:a','aac','-y',str(cls.clip)],check=True)
    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def window(self):
        w=Window(preview=True)
        w.settings=QSettings(str(Path(self.folder.name)/'settings.ini'),QSettings.Format.IniFormat)
        w.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.BypassWindowManagerHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        w.resize(1280,800);w.move(-5000,-5000);w.show()
        # Keep test audio inaudible; production audio remains enabled by default.
        w.play({'id':'fixture','name':'Embedded video verification','type':'movie'},'fixture',[{'url':self.clip.as_uri(),'name':'Local H.264 / AAC fixture'}])
        w.player.send('set_property','mute',True)
        return w

    def wait_frame(self,w):
        deadline=time.monotonic()+15;image=None
        while time.monotonic()<deadline:
            APP.processEvents();image=w.playback_view.video.grabFramebuffer()
            if w.player.position>.25 and w.playback_view.video.frames>2 and image and not image.isNull():
                colors={image.pixelColor(int(image.width()*x),int(image.height()*y)).rgb() for x in (.2,.35,.5,.65,.8) for y in (.25,.5,.75)}
                if len(colors)>5:return image
            time.sleep(.025)
        self.fail(f'No decoded video frames reached Luma’s framebuffer: position={w.player.position}, '
                  f'frames={w.playback_view.video.frames}, loaded={w.player.media_loaded}, loading={w.player.loading}')

    def test_real_video_is_inside_luma_and_controls_work(self):
        w=self.window()
        try:
            image=self.wait_frame(w)
            self.assertEqual(w.playback_view.video.window(),w)
            self.assertEqual([x for x in QApplication.topLevelWidgets() if x.isVisible()],[w])
            self.assertTrue(w.player.engine is not None)
            QTest.mouseClick(w.playback_view.play_button,Qt.MouseButton.LeftButton);w.player.seek(6)
            deadline=time.monotonic()+3
            while (not w.player.paused or w.player.position<5.8) and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
            self.assertTrue(w.player.paused);self.assertGreaterEqual(w.player.position,5.8)
            w.playback_view.volume.setValue(35)
            deadline=time.monotonic()+2
            while abs(w.player.volume-35)>1 and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
            self.assertAlmostEqual(w.player.volume,35,delta=1)
            self.assertGreaterEqual(len([t for t in w.player.tracks if t.get('type')=='audio']),1)
            w.player.send('set_property','sid','no')
            for _ in range(5):APP.processEvents();time.sleep(.025)
            w.playback_view.show_controls();APP.processEvents()
            output=Path(__file__).parents[1]/'artifacts'
            w.grab().save(str(output/'embedded-player.png'));image.save(str(output/'embedded-video-frame.png'))
            w.resize(1550,900);APP.processEvents();resized=w.playback_view.video.grabFramebuffer();self.assertGreater(resized.width(),image.width())
            w.toggle_fullscreen();APP.processEvents();self.assertTrue(w.isFullScreen())
            w.toggle_fullscreen();APP.processEvents();self.assertFalse(w.isFullScreen())
            w.stop_playback();APP.processEvents();self.assertFalse(w.player.streams);self.assertEqual(w.current,'Details')
        finally:w.close();APP.processEvents();self.assertIsNone(w.player.engine)

    def test_recording_keeps_native_video_and_mini_player_running(self):
        class QuietMini(MiniPlayer):
            def __init__(self,*args):
                super().__init__(*args)
                self.setWindowFlags(self.windowFlags()|Qt.WindowType.BypassWindowManagerHint|Qt.WindowType.WindowDoesNotAcceptFocus)
                self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            def move(self,*args):super().move(-5000,-5000)
        w=self.window()
        try:
            self.wait_frame(w);engine=w.player.engine;surface=w.playback_view.video;context=surface.render_context
            path=Path(self.folder.name)/'embedded-recording.mkv'
            w.settings.setValue('recordingDirectory',self.folder.name)
            QTest.mouseClick(w.playback_view.record_button,Qt.MouseButton.LeftButton)
            dialog=w._record_dialog;self.assertTrue(dialog.isVisible());dialog.move(-5000,-5000)
            before=w.player.position;frames=surface.frames;deadline=time.monotonic()+5
            while w.player.position<before+.3 and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
            self.assertGreater(w.player.position,before+.2);self.assertGreater(surface.frames,frames)
            dialog.findChild(QLineEdit,'fileNameEdit').setText(str(path));dialog.accept()
            self.assertTrue(w.player.recording)
            deadline=time.monotonic()+5
            while path.stat().st_size<1024 and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
            self.assertGreater(path.stat().st_size,1024)
            w.playback_view.show_controls();APP.processEvents()
            w.grab().save(str(Path(__file__).parents[1]/'artifacts/recording-embedded.png'))
            with patch('luma.MiniPlayer',QuietMini),patch.object(w,'home',lambda *args,**kwargs:None):
                w.enter_mini_player();self.wait_frame(w)
                self.assertTrue(w.player.recording);self.assertIs(w.player.engine,engine)
                self.assertIs(surface.render_context,context)
                QTest.mouseClick(w.playback_view.mini_record,Qt.MouseButton.LeftButton);APP.processEvents()
                self.assertFalse(w.player.recording);self.assertIs(w.player.engine,engine)
                w.restore_player();self.wait_frame(w)
            subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True)
        finally:w.close();APP.processEvents();self.assertIsNone(w.player.engine)

    def test_live_player_back_returns_to_the_same_cards(self):
        w=self.window()
        try:
            self.wait_frame(w)
            addon={'manifest':{'types':['tv'],'catalogs':[{'id':'channels','name':'Channels','type':'tv'}]}}
            w.client.state['addons']=[addon]
            title={'id':'fixture','name':'Fixture channel','type':'tv'}
            with patch.object(w.client,'catalog',return_value=[title]) as catalog:
                w.home('Live')
                deadline=time.monotonic()+3
                while not w.root.findChildren(MediaCard) and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
                root=w.root;card=root.findChild(MediaCard);self.assertIsNotNone(card)
                w.details(title,True)
                w.play(title,'fixture',[{'url':self.clip.as_uri(),'name':'Fixture'}])
                self.wait_frame(w);w.stop_playback();APP.processEvents()
                self.assertIs(w.root,root);self.assertIs(root.findChild(MediaCard),card)
                self.assertEqual(w.current,'Home');self.assertEqual(catalog.call_count,1)
                self.assertFalse(w.player.streams)
        finally:w.close();APP.processEvents();self.assertIsNone(w.player.engine)

    def test_mini_player_preserves_video_during_browsing_and_repeated_restore(self):
        class QuietMini(MiniPlayer):
            def __init__(self,*args):
                super().__init__(*args)
                self.setWindowFlags(self.windowFlags()|Qt.WindowType.BypassWindowManagerHint|Qt.WindowType.WindowDoesNotAcceptFocus)
                self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            def move(self,*args):super().move(-5000,-5000)
        w=self.window();w.activateWindow=lambda:None;w.raise_=lambda:None
        try:
            self.wait_frame(w)
            w.player.pause();w.player.seek(6)
            deadline=time.monotonic()+3
            while (not w.player.paused or w.player.position<5.8) and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
            engine=w.player.engine;surface=w.playback_view.video;context=surface.render_context
            with patch('luma.MiniPlayer',QuietMini),patch.object(w.client,'catalog',return_value=[]),patch.object(w.player,'load',wraps=w.player.load) as load:
                for _ in range(3):
                    position=w.player.position
                    w.enter_mini_player();APP.processEvents();mini=w.mini_window
                    self.wait_frame(w)
                    self.assertTrue(w.mini_mode);self.assertTrue(mini.windowFlags()&Qt.WindowType.WindowStaysOnTopHint)
                    self.assertIs(surface.window(),mini);self.assertIs(w.player.engine,engine)
                    self.assertIs(surface.render_context,context);self.assertTrue(w.player.paused)
                    self.assertAlmostEqual(w.player.position,position,delta=.4)
                    w.home('Movies');APP.processEvents();self.assertTrue(w.player.streams)
                    mini.resize(380,240);APP.processEvents()
                    self.assertTrue(w.playback_view.isVisible())
                    self.assertLessEqual(surface.width(),380,f'host={mini.size()} view={w.playback_view.size()} min={w.playback_view.minimumSizeHint()}')
                    if _==0:
                        w.showMinimized();APP.processEvents();self.assertTrue(mini.isVisible())
                        w.showNormal();APP.processEvents()
                        w.playback_view.show_controls();APP.processEvents()
                        mini.grab().save(str(Path(__file__).parents[1]/'artifacts/mini-player.png'))
                        QTest.mouseClick(w.playback_view.mini_pause,Qt.MouseButton.LeftButton)
                        deadline=time.monotonic()+2
                        while w.player.paused and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
                        self.assertFalse(w.player.paused)
                        QTest.mouseClick(w.playback_view.mini_pause,Qt.MouseButton.LeftButton)
                        deadline=time.monotonic()+2
                        while not w.player.paused and time.monotonic()<deadline:APP.processEvents();time.sleep(.02)
                    QTest.mouseClick(w.playback_view.restore_button,Qt.MouseButton.LeftButton);APP.processEvents()
                    self.assertFalse(w.mini_mode);self.assertIs(surface.window(),w)
                    self.assertIs(surface.render_context,context);self.assertIs(w.player.engine,engine)
                w.enter_mini_player();APP.processEvents();paused=w.player.paused
                QTest.mouseDClick(w.playback_view.mini_overlay,Qt.MouseButton.LeftButton);APP.processEvents()
                self.assertFalse(w.mini_mode);self.assertEqual(w.player.paused,paused)
                self.assertFalse(w.playback_view.click_timer.isActive())
                self.assertEqual(load.call_count,0)
                w.enter_mini_player();APP.processEvents();browse=w.root
                w.mini_window.close();APP.processEvents()
                self.assertFalse(w.mini_mode);self.assertFalse(w.player.streams);self.assertIsNone(w.play_title)
                self.assertIs(w.root,browse)
                # A finished Live stream closes only PiP and preserves browsing.
                w.play({'id':'fixture','name':'Channel','type':'tv'},'fixture',[{'url':self.clip.as_uri(),'name':'Fixture'}])
                self.wait_frame(w);w.enter_mini_player();APP.processEvents();browse=w.root
                w.playback_finished(True);APP.processEvents()
                self.assertFalse(w.mini_mode);self.assertIs(w.root,browse);self.assertFalse(w.player.streams)
                # Closing the main window also disposes a still-open mini player.
                w.play({'id':'fixture','name':'Close test','type':'movie'},'fixture',[{'url':self.clip.as_uri(),'name':'Fixture'}])
                self.wait_frame(w);w.enter_mini_player();APP.processEvents();w.close();APP.processEvents()
                self.assertIsNone(w.mini_window);self.assertIsNone(w.player.engine)
        finally:w.close();APP.processEvents()

    def test_repeated_playback_and_source_switch_cleanup(self):
        w=self.window()
        try:
            self.wait_frame(w)
            engine=w.player.engine;surface=w.playback_view.video
            for _ in range(3):
                w.play({'id':'fixture','name':'Reopen test','type':'movie'},'fixture',[{'url':self.clip.as_uri(),'name':'Fixture'}],resume=2)
                self.wait_frame(w)
                self.assertIs(w.player.engine,engine);self.assertIs(w.playback_view.video,surface)
                w.home();APP.processEvents();self.assertFalse(w.player.streams)
            w.home();APP.processEvents();self.assertFalse(w.player.streams)
        finally:w.close();APP.processEvents();self.assertIsNone(w.player.engine)

if __name__=='__main__':unittest.main()
