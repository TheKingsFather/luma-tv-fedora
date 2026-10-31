"""Section visits retain their browse widgets; Back performs no network refresh."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication,QScrollArea,QPushButton
from PyQt6.QtGui import QPixmap,QColor
from PyQt6 import sip
from luma import Window
from backend import Client
from cards import MediaCard,ResponsiveGrid

APP=QApplication.instance() or QApplication([])
CAT={'id':'channels','type':'tv','name':'Live channels','extraSupported':['skip']}
ADDON={'transportUrl':'https://fixture.invalid/manifest.json','manifest':{'name':'Fixture','types':['tv'],'catalogs':[CAT]}}
ITEMS=[{'id':str(i),'name':f'Channel {i}','type':'tv'} for i in range(65)]

class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.refresh=patch.object(Client,'refresh',return_value=None).start()
        self.refresh_addons=patch.object(Client,'refresh_addons',return_value=None).start()
        self.catalog=patch.object(Client,'catalog',side_effect=lambda a,c,skip=0:ITEMS[skip:skip+30]).start()
        self.meta=patch.object(Client,'meta',side_effect=lambda title:title).start()
        self.w=Window(preview=True)
        # Deliver deterministic workers on the Qt thread; no real account/network.
        self.pending=[]
        self.w.work=lambda f,success=lambda _:None,failure=None,token=None,pool=None:self.pending.append((f,success,failure,self.w.generation if token is None else token))
        self.w.client.state.update(key='fixture',name='Fixture',addons=[ADDON])
        self.w.show();self.w.home('Live');self.flush()
    def tearDown(self):
        self.w.play_title=None;self.w.close();APP.processEvents();self.w.client.pool.shutdown(wait=True)
        patch.stopall()
    def flush(self):
        while self.pending:
            f,success,failure,token=self.pending.pop(0)
            try:result=(f(),None)
            except Exception as e:result=(None,e)
            self.w.deliver(success,failure,result,token)
        APP.processEvents();APP.processEvents()
    def open_catalog(self):
        self.w.catalog_page(ADDON,CAT);self.flush()
        return self.w.root
    def pretend_play(self):
        # Navigation coverage independent of the GL engine integration tests.
        self.w.page();self.w.current='Playing';self.w.play_title=ITEMS[0];self.w.play_key=''

    def test_back_restores_grid_artwork_pagination_and_scroll_without_requests(self):
        home=self.w.root;catalog=self.open_catalog()
        sc=catalog.findChild(QScrollArea)
        more=next(b for b in catalog.findChildren(QPushButton) if b.text()=='Load more')
        more.click();self.flush()
        self.assertEqual(len(catalog.findChildren(MediaCard)),60)
        sc.verticalScrollBar().setValue(950);position=sc.verticalScrollBar().value();self.assertGreater(position,0)
        card=catalog.findChildren(MediaCard)[20];pix=QPixmap(120,60);pix.fill(QColor('red'));card.art.setPixmap(pix)
        requests=self.catalog.call_count
        for _ in range(3):
            self.w.details(ITEMS[20],True);self.pretend_play();self.w.stop_playback();APP.processEvents()
            self.assertIs(self.w.root,catalog);self.assertEqual(self.w.current,'Catalog')
            self.assertEqual(sc.verticalScrollBar().value(),position)
            self.assertIs(catalog.findChildren(MediaCard)[20],card);self.assertFalse(card.art.source.isNull())
            self.assertEqual(len(catalog.findChildren(MediaCard)),60)
        self.assertEqual(self.catalog.call_count,requests);self.assertEqual(self.refresh_addons.call_count,1)
        self.w.back();self.assertIs(self.w.root,home);self.assertEqual(self.refresh_addons.call_count,1)

    def test_live_same_tab_and_details_back_reuse_home_horizontal_scroll(self):
        root=self.w.root;row=next(sc for sc in root.findChildren(QScrollArea) if sc.horizontalScrollBar().maximum()>0)
        row.horizontalScrollBar().setValue(900);position=row.horizontalScrollBar().value()
        self.w.home('Live');self.assertIs(self.w.root,root)
        self.w.details(ITEMS[0],True);self.w.back();APP.processEvents()
        self.assertIs(self.w.root,root);self.assertEqual(row.horizontalScrollBar().value(),position)
        self.assertEqual(self.refresh_addons.call_count,1);self.assertEqual(self.catalog.call_count,1)

    def test_leaving_section_invalidates_cache_and_return_refreshes_once(self):
        root=self.open_catalog();self.w.details(ITEMS[0],True)
        self.w.home('Movies');self.flush();self.w.home('Live');self.flush()
        self.assertIsNot(self.w.root,root);self.assertEqual(self.refresh_addons.call_count,2)
        self.assertEqual(self.catalog.call_count,3) # Live overview, full grid, new visit.
        self.w.details(ITEMS[0],True);self.w.back();self.assertEqual(self.refresh_addons.call_count,2)

    def test_late_catalog_result_updates_hidden_cache_without_navigation(self):
        self.w.home('Movies');self.flush();self.w.home('Live')
        # Finish manifests, leave before the catalog response is delivered.
        f,success,failure,token=self.pending.pop(0);self.w.deliver(success,failure,(f(),None),token)
        root=self.w.root;self.w.settings_page();active=self.w.root;active_token=self.w.generation
        self.flush()
        self.assertIs(self.w.root,active);self.assertEqual(self.w.generation,active_token)
        self.assertEqual(self.w.current,'Settings');self.assertEqual(len(root.findChildren(MediaCard)),14)
        self.w.back();self.assertIs(self.w.root,root);self.assertIsNotNone(self.w.hero)
        self.assertEqual(self.refresh_addons.call_count,2)

    def test_old_section_response_is_discarded_and_live_eof_returns_to_cache(self):
        self.w.home('Movies');self.flush();self.w.home('Live');self.w.home('Series');self.flush()
        self.assertEqual(self.w.tab,'Series');self.assertEqual(self.w.current,'Home')
        self.assertEqual(len(self.w.root.findChildren(MediaCard)),0)
        self.w.home('Live');self.flush();root=self.open_catalog();calls=self.catalog.call_count
        self.w.details(ITEMS[0],True);self.pretend_play();self.w.playback_finished(True)
        self.assertIs(self.w.root,root);self.assertEqual(self.w.current,'Catalog')
        self.assertEqual(self.catalog.call_count,calls)

if __name__=='__main__':unittest.main()
