import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap,QColor,QPainter,QIcon
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QScrollArea
from PyQt6.QtTest import QTest
from cards import Artwork,MediaCard,ResponsiveGrid
from pathlib import Path

APP=QApplication.instance() or QApplication([])

class ArtworkTests(unittest.TestCase):
    def test_wide_preview_retains_both_edges_in_portrait_frame(self):
        source=QPixmap(420,100);source.fill(QColor('white'));p=QPainter(source)
        p.fillRect(0,0,30,100,QColor('red'));p.fillRect(390,0,30,100,QColor('blue'));p.end()
        art=Artwork('Fixture');art.resize(240,187);art.setPixmap(source);art.show();APP.processEvents()
        image=art.grab().toImage()
        self.assertGreater(image.pixelColor(10,93).red(),220)
        self.assertGreater(image.pixelColor(230,93).blue(),220)
        self.assertEqual(art.source.size(),source.size());art.close()

    def test_live_cards_are_wide_and_keyboard_activatable(self):
        calls=[];card=MediaCard({'type':'sport','name':'Full event name'},lambda:calls.append(True),248)
        card.show();card.setFocus();APP.processEvents()
        self.assertGreater(card.art.width(),card.art.height())
        QTest.keyClick(card,Qt.Key.Key_Return);self.assertEqual(calls,[True]);card.close()

    def test_grid_reflows_when_viewport_grows_and_shrinks(self):
        window=QWidget();box=QVBoxLayout(window);sc=QScrollArea();sc.setWidgetResizable(True);content=QWidget();layout=QVBoxLayout(content);sc.setWidget(content);box.addWidget(sc)
        grid=ResponsiveGrid([{'type':'tv','name':str(i)} for i in range(12)],lambda t:MediaCard(t,lambda:None));layout.addWidget(grid)
        window.resize(1800,900);window.show();APP.processEvents();APP.processEvents();wide=grid.columns
        window.resize(1000,800);APP.processEvents();APP.processEvents();narrow=grid.columns
        self.assertGreater(wide,narrow)
        self.assertLessEqual(narrow*grid.cards[0].width()+18*(narrow-1),grid.width())
        self.assertEqual(grid.grid.count(),12);window.close()

    def test_logo_renders_at_launcher_sizes(self):
        icon=QIcon(str(Path(__file__).parents[1]/'luma.svg'))
        for size in (16,32,64,512):self.assertFalse(icon.pixmap(size,size).isNull())

if __name__=='__main__':unittest.main()
