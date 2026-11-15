"""Resolution events describe the playing video, independent of provider labels."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock,MagicMock,patch
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication,QWidget
from player import Player
from player_view import PlaybackView
APP=QApplication.instance() or QApplication([])
class Surface(QWidget):
    failure=pyqtSignal(str)
    def __init__(self,player,parent=None):super().__init__(parent)
class QualityTests(unittest.TestCase):
    def test_decoded_resolution_changes_and_unknown(self):
        player=Player();player.engine=MagicMock();player.streams=[{'name':'Misleading 4K label'}]
        with patch('player_view.VideoSurface',Surface):
            view=PlaybackView(player,'Quality fixture',*[Mock() for _ in range(6)])
        try:
            for height in (720,1080,1440,2160):
                player._receive(player.generation,dict(event='property-change',name='video-params',data={'w':height*16//9,'h':height}))
                self.assertEqual(view.quality.text(),f'{height}p')
                self.assertEqual(view.mini_quality.text(),f'{height}p')
            player._receive(player.generation,dict(event='property-change',name='video-params',data=None))
            self.assertEqual(view.quality.text(),'—')
            for invalid in ({'w':1920,'h':0},{'w':'1920','h':1080},{'w':True,'h':1080}):
                player.set_quality(invalid);self.assertEqual(player.quality,'')
            player.set_quality({'w':1920,'h':1080});player.stop()
            self.assertEqual(view.mini_quality.text(),'—')
        finally:view.close();view.deleteLater()
    def test_source_change_clears_previous_resolution(self):
        player=Player();player.engine=MagicMock();player.ready=True;player.streams=[{'url':'https://example.test/video'}]
        player.set_quality({'w':2560,'h':1440});player.load()
        self.assertEqual(player.quality,'');player.stop()
