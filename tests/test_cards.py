import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PyQt6.QtCore import Qt,QEvent
from PyQt6.QtGui import QPixmap,QColor,QPainter,QIcon
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QScrollArea
from PyQt6.QtTest import QTest
from cards import Artwork,MediaCard,ResponsiveGrid,CardRow
from pathlib import Path

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
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

    def test_hover_debounce_expansion_and_collapse_preserve_height(self):
        card=MediaCard({'name':'Movie','type':'movie'},lambda:None);card.show()
        card.activateWindow();QTest.qWait(50);card.clearFocus();card.collapse();width=card.width();height=card.height();requests=[]
        card.preview_requested.connect(lambda:requests.append(1))
        APP.sendEvent(card,QEvent(QEvent.Type.Enter));QTest.qWait(100)
        self.assertEqual(card.width(),width)
        APP.sendEvent(card,QEvent(QEvent.Type.Leave));QTest.qWait(400)
        self.assertEqual(card.width(),width);self.assertFalse(requests)
        APP.sendEvent(card,QEvent(QEvent.Type.Enter));QTest.qWait(650)
        self.assertGreater(card.width(),width*2);self.assertEqual(card.height(),height)
        self.assertEqual(len(requests),1)
        APP.sendEvent(card,QEvent(QEvent.Type.Leave));card.clearFocus();QTest.qWait(300)
        self.assertEqual(card.width(),width);card.close()

    def test_row_keyboard_focus_scrolls_expanded_card_into_view(self):
        cards=[MediaCard({'name':str(i),'type':'movie'},lambda:None) for i in range(8)]
        row=CardRow(cards);row.resize(550,row.height());row.show();row.activateWindow();QTest.qWait(50)
        cards[-2].setFocus();QTest.qWait(650)
        self.assertTrue(cards[-2].preview_target)
        QTest.keyClick(cards[-2],Qt.Key.Key_Right);QTest.qWait(650)
        self.assertTrue(cards[-1].hasFocus());self.assertTrue(cards[-1].preview_target)
        self.assertFalse(cards[-2].preview_target)
        right=cards[-1].mapTo(row.viewport(),cards[-1].rect().bottomRight()).x()
        self.assertLessEqual(right,row.viewport().width());self.assertGreater(row.horizontalScrollBar().value(),0)
        row.resize(300,row.height());QTest.qWait(100)
        self.assertLessEqual(cards[-1].width(),row.viewport().width())
        row.close()

    def test_grid_preview_stays_inside_viewport_and_keyboard_navigation_works(self):
        grid=ResponsiveGrid([{'name':str(i),'type':'movie'} for i in range(12)],lambda t:MediaCard(t,lambda:None))
        grid.resize(720,500);grid.show();grid.activateWindow();QTest.qWait(50);columns=grid.columns
        card=grid.cards[columns-1];height=grid.height();card.setFocus();QTest.qWait(650)
        self.assertTrue(card.preview_target);self.assertGreater(card.width(),card.base_width)
        self.assertGreaterEqual(card.x(),0);self.assertLessEqual(card.geometry().right(),grid.width())
        self.assertEqual(grid.height(),height);self.assertEqual(grid.columns,columns)
        QTest.keyClick(card,Qt.Key.Key_Down);QTest.qWait(650)
        self.assertTrue(grid.cards[2*columns-1].hasFocus());self.assertFalse(card.preview_target)
        grid.close()

    def test_expanded_backdrop_is_used_without_replacing_the_original_poster(self):
        card=MediaCard({'name':'Preview','type':'movie'},lambda:None)
        poster=QPixmap(100,150);poster.fill(QColor('red'))
        backdrop=QPixmap(400,225);backdrop.fill(QColor('blue'))
        card.art.setPixmap(poster);card.art.setPreview(backdrop);card.previewProgress=1
        image=card.art.grab().toImage()
        self.assertGreater(image.pixelColor(image.width()//2,15).blue(),200)
        self.assertEqual(card.art.source.toImage().pixelColor(0,0),QColor('red'))
        card.close()

    def test_vertical_arrow_moves_between_home_rows(self):
        window=QWidget();box=QVBoxLayout(window)
        rows=[CardRow([MediaCard({'name':str(i),'type':'movie'},lambda:None) for i in range(3)]) for _ in range(2)]
        for row in rows:box.addWidget(row)
        window.show();window.activateWindow();QTest.qWait(50)
        rows[0].cards[1].setFocus();QTest.keyClick(rows[0].cards[1],Qt.Key.Key_Down);APP.processEvents()
        self.assertTrue(rows[1].cards[1].hasFocus())
        QTest.keyClick(rows[1].cards[1],Qt.Key.Key_Up);APP.processEvents()
        self.assertTrue(rows[0].cards[1].hasFocus());window.close()

if __name__=='__main__':unittest.main()
