import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from cryptography.fernet import Fernet, InvalidToken
from PyQt6.QtWidgets import QApplication, QLabel, QComboBox
from backend import Client, Vault, supports, resource_url, browseable, future_video, unwrap, ApiError, live_catalog, catalog_choices
from player import Player

APP=QApplication.instance() or QApplication([])

class ProtocolTests(unittest.TestCase):
    def test_anime_and_download_libraries_are_not_live(self):
        for kind in ('anime','hentai','other','movie','series'):
            self.assertFalse(live_catalog({'type':kind,'id':'top','name':'Popular'}))
        self.assertFalse(live_catalog({'type':'anime','name':'Livechart anime','id':'airing'}))
    def test_explicit_live_categories(self):
        for kind in ('tv','channel','sport','sports','events','iptv'):
            self.assertTrue(live_catalog({'type':kind,'id':'football','name':'Channels'}))
    def test_tv_replays_and_highlights_are_not_live(self):
        for name in ('Replays','Highlights','Catchup','VOD','Archive'):
            self.assertFalse(live_catalog({'type':'tv','id':'provider_'+name.lower(),'name':name}))
    def test_live_catalogs_are_not_cut_off_after_eight_rows(self):
        vod={'manifest':{'catalogs':[{'id':str(i),'type':'anime'} for i in range(12)]}}
        channels={'manifest':{'catalogs':[{'id':str(i),'type':'tv','name':'Channel group'} for i in range(15)]}}
        choices=catalog_choices([vod,channels],'Live')
        self.assertEqual(len(choices),15)
        self.assertTrue(all(c['type']=='tv' for a,c in choices))
    def test_nullable_extra_lists(self):
        self.assertTrue(browseable({'extra':None,'extraRequired':None}))
    def test_catalog_items_inherit_live_type_when_omitted(self):
        c=Client()
        try:
            with patch('backend.request',return_value={'metas':[{'id':'channel1','name':'News'}]}):
                rows=c.catalog({'transportUrl':'https://example.org/manifest.json'},{'id':'channels','type':'tv'})
                self.assertEqual(rows[0]['type'],'tv')
        finally:c.pool.shutdown()
    def test_live_manifest_hydration_and_offline_fallback(self):
        c=Client();a={'transportUrl':'https://example.org/manifest.json','manifest':{'id':'live.example','types':['tv'],'catalogs':[]}}
        try:
            with patch('backend.request',return_value={'id':'live.example','types':['tv'],'catalogs':[{'id':'channels','type':'tv'}]}):
                latest=c.current_manifests([a]);self.assertEqual(len(catalog_choices(latest,'Live')),1)
            with patch('backend.request',side_effect=OSError('Offline')):self.assertEqual(c.current_manifests(latest),latest)
        finally:c.pool.shutdown()
    def test_capabilities(self):
        a={'manifest':{'types':['movie','series'],'resources':[{'name':'stream','types':['series'],'idPrefixes':['tt']}]}}
        self.assertTrue(supports(a,'stream','series','tt1:1:2'))
        self.assertFalse(supports(a,'stream','movie','tt1'))
        self.assertFalse(supports(a,'stream','series','other'))
    def test_empty_prefixes_deny(self):
        self.assertFalse(supports({'manifest':{'resources':['stream'],'idPrefixes':[]}},'stream','movie','tt1'))
    def test_url_encoding(self):
        a={'transportUrl':'https://example.org/private/manifest.json'}
        self.assertEqual(resource_url(a,'stream','series','tt1:1:2'),'https://example.org/private/stream/series/tt1:1:2.json')
        self.assertIn('a%2Fb',resource_url(a,'meta','movie','a/b'))
    def test_required_search_not_browseable(self):
        self.assertFalse(browseable({'extra':[{'name':'search','isRequired':True}]}))
        self.assertTrue(browseable({'extra':[{'name':'skip'}]}))
    def test_future_episodes(self):
        self.assertTrue(future_video({'released':'2099-01-01T00:00:00Z'}))
        self.assertFalse(future_video({'released':'2000-01-01T00:00:00Z'}))
    def test_pending_error(self):
        with self.assertRaises(ApiError) as c:unwrap({'error':{'code':101,'message':'Pending'}})
        self.assertEqual(c.exception.code,101)
    def test_metadata_merges_without_duplicate_keys(self):
        c=Client();c.state['addons']=[{'transportUrl':'https://example.org/manifest.json','manifest':{'resources':['meta'],'types':['movie']}}]
        try:
            with patch('backend.request',return_value={'meta':{'id':'tt1','type':'movie','description':'Full metadata'}}):
                self.assertEqual(c.meta({'id':'tt1','type':'movie'})['description'],'Full metadata')
        finally:c.pool.shutdown()
    def test_only_direct_streams(self):
        c=Client()
        try:
            out=c.streams({'type':'movie'},'tt1',[{'infoHash':'abc'},{'url':'javascript:bad'},{'url':'https://example.org/a','behaviorHints':{'proxyHeaders':{'request':{'Referer':'https://example.org'}}}}])
            self.assertEqual(len(out),1);self.assertEqual(out[0]['behaviorHints']['proxyHeaders']['request']['Referer'],'https://example.org')
        finally:c.pool.shutdown()
    def test_encrypted_atomic_state(self):
        with tempfile.TemporaryDirectory() as d:
            v=Vault(Path(d)/'session.enc');v.cipher=Fernet(Fernet.generate_key());v.save({'key':'private-test-token'})
            self.assertNotIn(b'private-test-token',v.path.read_bytes());self.assertEqual(v.load()['key'],'private-test-token');self.assertEqual(v.path.stat().st_mode&0o777,0o600)
            v.path.write_bytes(b'corrupted')
            with self.assertRaises(InvalidToken):v.load()
    def test_resume_completion(self):
        c=Client();c.state['library']={'tt1':{'_id':'tt1','state':{'video_id':'tt1:1:2','timeOffset':5000,'duration':10000}}}
        self.assertEqual(c.resume('tt1','tt1:1:2'),5);self.assertEqual(c.resume('tt1','tt1:1:1'),0)
        c.state['library']['tt1']['state']['timeOffset']=9900
        self.assertEqual(c.resume('tt1','tt1:1:2'),0);c.pool.shutdown()
    def test_library_queue_survives_offline(self):
        with tempfile.TemporaryDirectory() as d:
            v=Vault(Path(d)/'session.enc');v.cipher=Fernet(Fernet.generate_key());c=Client(v);c.state['key']='fixture-token'
            try:
                with patch.object(c,'api',side_effect=OSError('Offline')):
                    self.assertTrue(c.toggle({'id':'tt1','name':'Fixture','type':'movie'}))
                self.assertIn('tt1',c.state['pending']);self.assertIn('tt1',v.load()['pending'])
                with patch.object(c,'api',return_value={}):c.flush()
                self.assertFalse(c.state['pending'])
            finally:c.pool.shutdown()

class LiveTests(unittest.TestCase):
    def test_public_link_and_catalog(self):
        c=Client()
        try:
            link=c.create_link();self.assertTrue(link['link'].startswith('https://link.stremio.com/'));self.assertEqual(c.read_link(link['code']),'')
            c.refresh();a,cat=next((a,b) for a,b in c.catalogs() if browseable(b));self.assertTrue(c.catalog(a,cat))
        finally:c.pool.shutdown()
    def test_native_ui_browse_and_details(self):
        from luma import Window,STYLE
        APP.setStyleSheet(STYLE);w=Window(preview=True);w.show()
        try:
            end=time.monotonic()+25
            while not w.hero and time.monotonic()<end:APP.processEvents();time.sleep(.03)
            self.assertIsNotNone(w.hero)
            w.grab().save(str(Path(__file__).parents[1]/'artifacts/test-home.png'))
            title={'id':'fixture','name':'Episode navigation','type':'series','description':'Fixture','videos':[{'id':'fixture:1:1','season':1,'episode':1,'title':'Pilot'},{'id':'fixture:2:1','season':2,'episode':1,'title':'Return'}]}
            w.details(title,True);APP.processEvents();self.assertEqual(w.current,'Details');self.assertTrue(w.findChildren(QComboBox));self.assertTrue(any('Pilot' in b.text() for b in w.findChildren(__import__('PyQt6.QtWidgets',fromlist=['QPushButton']).QPushButton)))
        finally:w.close();APP.processEvents()
    def test_in_process_play_pause_seek_without_child_player(self):
        with tempfile.TemporaryDirectory() as d:
            clip=Path(d)/'fixture.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24','-t','8','-c:v','libx264','-preset','ultrafast','-y',str(clip)],check=True)
            p=Player();p.headless=True
            try:
                with patch('subprocess.Popen',side_effect=AssertionError('External player launched')):
                    p.start([{'url':clip.as_uri(),'name':'Local fixture'}])
                end=time.monotonic()+12
                while p.position<.3 and time.monotonic()<end:APP.processEvents();time.sleep(.02)
                self.assertGreater(p.position,.2);self.assertEqual(Path(p.folder.name).stat().st_mode&0o777,0o700)
                p.pause();p.seek(4);end=time.monotonic()+3
                while (not p.paused or p.position<3.8) and time.monotonic()<end:APP.processEvents();time.sleep(.02)
                self.assertTrue(p.paused);self.assertGreaterEqual(p.position,3.8)
            finally:p.shutdown()

if __name__=='__main__':unittest.main()
