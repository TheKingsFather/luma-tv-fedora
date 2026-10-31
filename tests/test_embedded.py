"""Real GL video tests; run in a separate xcb test process, off the visible desktop."""
import os
import time
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from luma import Window,STYLE
from cards import MediaCard

APP=QApplication.instance() or QApplication([])
APP.setStyle('Fusion');APP.setStyleSheet(STYLE)

@unittest.skipUnless(os.environ.get('QT_QPA_PLATFORM')=='xcb','Real OpenGL requires the isolated xcb test run')
class EmbeddedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='luma-render-test-')
        cls.clip=Path(cls.folder.name)/'test.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24','-f','lavfi','-i','sine=frequency=330:sample_rate=48000','-t','18','-c:v','libx264','-preset','ultrafast','-c:a','aac','-y',str(cls.clip)],check=True)
    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def window(self):
        w=Window(preview=True)
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
        self.fail('No decoded video frames reached Luma’s framebuffer')

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
