"""Stremio protocol and private desktop state, independent of the UI."""
import concurrent.futures as futures
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from cryptography.fernet import Fernet
from desktop_storage import default_vault_path, load_vault_key, store_vault_key

UA = 'LumaDesktop/0.1 (Fedora Linux)'
API = 'https://api.strem.io/api/'
LINK = 'https://link.stremio.com/api/v2/'

class ApiError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)

def request(url, body=None):
    if urlsplit(url).scheme not in ('http', 'https'):
        raise ValueError('Unsupported address')
    with requests.request('POST' if body is not None else 'GET', url, json=body,
                          headers={'User-Agent': UA}, timeout=(10, 18), stream=True) as r:
        r.raise_for_status()
        data = bytearray()
        for chunk in r.iter_content(65536):
            data.extend(chunk)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError('Response too large')
        return json.loads(data)

def unwrap(value):
    if value.get('error'):
        e = value['error']
        raise ApiError(e.get('code'), e.get('message', 'Stremio request failed'))
    return value.get('result', value)

def supports(addon, resource, kind, ident):
    m = addon.get('manifest', {})
    for r in m.get('resources', []):
        if (r.get('name') if isinstance(r, dict) else r) != resource:
            continue
        opts = r if isinstance(r, dict) else {}
        types = opts.get('types', m.get('types'))
        prefixes = opts.get('idPrefixes', m.get('idPrefixes'))
        if types is not None and kind not in types:
            continue
        if prefixes is None or any(ident.startswith(p) for p in prefixes):
            return True
    return False

def resource_url(addon, resource, kind, ident, extras=''):
    base = addon['transportUrl'].removesuffix('/manifest.json').rstrip('/')
    path = '/'.join(quote(str(v), safe=':') for v in (resource, kind, ident))
    return f'{base}/{path}' + (f'/{extras}' if extras else '') + '.json'

def extra(catalog, name):
    return name in (catalog.get('extraSupported') or []) or name in (catalog.get('extraRequired') or []) or any(e.get('name') == name for e in (catalog.get('extra') or []))

LIVE_TYPES = {'tv', 'channel', 'channels', 'live', 'iptv', 'sport', 'sports', 'event', 'events'}

def live_catalog(catalog):
    """Custom media types are not inherently live (anime/other are common VOD types)."""
    kind = str(catalog.get('type', '')).lower()
    words = set(re.findall(r'[a-z]+', str(catalog.get('id', ''))+' '+str(catalog.get('name', '')), re.I))
    words = {w.lower() for w in words}
    if words & {'replay', 'replays', 'highlights', 'highlight', 'catchup', 'vod', 'archive', 'archives'}:
        return False
    return kind in LIVE_TYPES

def catalog_choices(addons, tab):
    choices = [(a, c) for a in addons for c in (a.get('manifest', {}).get('catalogs') or [])
               if browseable(c) and (tab == 'Home' or
                   tab == 'Movies' and c.get('type') == 'movie' or
                   tab == 'Series' and c.get('type') == 'series' or
                   tab == 'Live' and live_catalog(c))]
    return choices if tab == 'Live' else choices[:8]

def browseable(catalog):
    return not catalog.get('extraRequired') and not any(e.get('isRequired') for e in (catalog.get('extra') or []))

def future_video(video):
    try:
        return datetime.fromisoformat(video.get('released', '').replace('Z', '+00:00')) > datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

class Vault:
    """The Fernet key lives in the desktop keyring; the account bundle is encrypted."""
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_vault_path()
        self.cipher = None

    def unlock(self, create=False):
        if self.cipher:
            return
        key = load_vault_key()
        if not key and create:
            if self.path.exists():
                raise RuntimeError('The saved connection needs its original desktop keyring.')
            key = Fernet.generate_key()
            store_vault_key(key)
        if key:
            self.cipher = Fernet(key)

    def load(self):
        if not self.path.exists():
            return {}
        self.unlock()
        if not self.cipher:
            raise RuntimeError('Unlock your desktop keyring to restore Stremio.')
        return json.loads(self.cipher.decrypt(self.path.read_bytes()))

    def save(self, value):
        self.unlock(create=True)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(self.cipher.encrypt(json.dumps(value).encode()))
            out.flush()
            os.fsync(out.fileno())
        temporary.replace(self.path)

    def clear(self):
        self.path.unlink(missing_ok=True)
        self.cipher = None
        # The encryption key can be reused for a subsequent connection on this desktop.

class Client:
    def __init__(self, vault=None):
        self.vault = vault or Vault()
        self.state = {'key': '', 'name': '', 'addons': [], 'library': {}, 'pending': {}}
        self.pool = futures.ThreadPoolExecutor(8)
        self.lock = threading.RLock()

    @property
    def connected(self):
        return bool(self.state.get('key'))

    @property
    def addons(self):
        return self.state.get('addons', [])

    def restore(self):
        with self.lock:
            self.state.update(self.vault.load())

    def persist(self):
        if self.connected:
            self.vault.save(self.state)

    def create_link(self):
        value = unwrap(request(LINK + 'create?type=Create'))
        if urlsplit(value.get('link', '')).netloc != 'link.stremio.com':
            raise ValueError('Unexpected pairing address')
        return value

    def read_link(self, code):
        try:
            return unwrap(request(LINK + 'read?type=Read&code=' + quote(code, safe=''))).get('authKey', '')
        except ApiError as e:
            if e.code == 101:
                return ''
            raise

    def api(self, name, **body):
        return unwrap(request(API + name, body))

    def connect(self, key):
        user = self.api('getUser', type='GetUser', authKey=key)
        addons = self.current_manifests(self.api('addonCollectionGet', type='AddonCollectionGet', authKey=key, update=True).get('addons', []))
        library = self.api('datastoreGet', authKey=key, collection='libraryItem', ids=[], all=True)
        name = user.get('fullname') or user.get('email', 'Your Stremio').split('@')[0]
        value = {'key': key, 'name': name, 'addons': addons, 'library': {i['_id']: i for i in library}, 'pending': {}}
        with self.lock:
            self.vault.save(value)
            self.state = value

    def refresh(self):
        with self.lock:
            if not self.connected:
                manifest = request('https://v3-cinemeta.strem.io/manifest.json')
                self.state['addons'] = [{'transportUrl': 'https://v3-cinemeta.strem.io/manifest.json', 'manifest': manifest}]
                return
            self.flush()
            key = self.state['key']
            addons = self.current_manifests(self.api('addonCollectionGet', type='AddonCollectionGet', authKey=key, update=True).get('addons', []))
            items = self.api('datastoreGet', authKey=key, collection='libraryItem', ids=[], all=True)
            self.state['addons'] = addons
            self.state['library'] = {i['_id']: i for i in items} | self.state['pending']
            self.persist()

    def current_manifests(self, addons):
        """Refresh live providers at their configured URL; never change their account config."""
        def latest(addon):
            manifest = addon.get('manifest', {})
            if not (set(manifest.get('types') or []) & LIVE_TYPES or
                    any(live_catalog(c) for c in (manifest.get('catalogs') or []))):
                return addon
            try:
                fresh = request(addon['transportUrl'])
                if fresh.get('id') and isinstance(fresh.get('catalogs'), list):
                    return dict(addon, manifest=manifest | fresh)
            except Exception:
                pass  # An offline provider keeps its last known manifest.
            return addon
        return list(self.pool.map(latest, addons))

    def refresh_addons(self):
        """Read-only account refresh, separate from library flushes."""
        with self.lock:
            if not self.connected:
                return
            addons = self.api('addonCollectionGet', type='AddonCollectionGet', authKey=self.state['key'], update=True).get('addons', [])
            self.state['addons'] = self.current_manifests(addons)
            self.persist()

    def disconnect(self):
        with self.lock:
            self.vault.clear()
            self.state = {'key': '', 'name': '', 'addons': [], 'library': {}, 'pending': {}}

    def catalogs(self):
        return [(a, c) for a in self.addons for c in a.get('manifest', {}).get('catalogs', [])]

    def catalog(self, addon, catalog, skip=0):
        extras = f'skip={skip}' if skip else ''
        items = request(resource_url(addon, 'catalog', catalog['type'], catalog['id'], extras)).get('metas', [])
        return [dict(item, type=item.get('type') or catalog['type']) for item in items]

    def search(self, query):
        jobs = [self.pool.submit(request, resource_url(a, 'catalog', c['type'], c['id'], 'search=' + quote(query, safe=''))) for a, c in self.catalogs() if extra(c, 'search')]
        found, successful = {}, 0
        for f in futures.as_completed(jobs):
            try:
                for t in f.result().get('metas', []):
                    found[(t.get('type', 'movie'), t['id'])] = t
                successful += 1
            except Exception:
                pass
        if jobs and not successful:
            raise RuntimeError('Search providers are unavailable. Try again shortly.')
        return list(found.values())

    def meta(self, title):
        ident, kind = title.get('id', title.get('_id')), title.get('type', 'movie')
        for a in self.addons:
            if supports(a, 'meta', kind, ident):
                try:
                    result = request(resource_url(a, 'meta', kind, ident)).get('meta')
                    if result:
                        merged = dict(title) | result
                        merged.setdefault('id', ident)
                        merged.setdefault('type', kind)
                        return merged
                except Exception:
                    continue
        return title

    def streams(self, title, video_id, included=None):
        jobs = []
        if included:
            results = [('Included source', included)]
        else:
            for a in self.addons:
                if supports(a, 'stream', title.get('type', 'movie'), video_id):
                    jobs.append((a['manifest'].get('name', 'Add-on'), self.pool.submit(request, resource_url(a, 'stream', title.get('type', 'movie'), video_id))))
            results = []
            for name, f in jobs:
                try:
                    results.append((name, f.result().get('streams', [])))
                except Exception:
                    pass
        out, seen = [], set()
        for provider, streams in results:
            for s in streams:
                url = s.get('url', '')
                if urlsplit(url).scheme in ('http', 'https') and url not in seen:
                    out.append(dict(s, provider=provider))
                    seen.add(url)
        return out

    def subtitles(self, title, video_id):
        jobs = [self.pool.submit(request, resource_url(a, 'subtitles', title.get('type', 'movie'), video_id)) for a in self.addons if supports(a, 'subtitles', title.get('type', 'movie'), video_id)]
        result = []
        for f in jobs:
            try:
                result.extend(f.result().get('subtitles', []))
            except Exception:
                pass
        return result

    def library(self, continuing=False):
        items = list(self.state['library'].values())
        items.sort(key=lambda i: i.get('state', {}).get('lastWatched', ''), reverse=True)
        result = []
        for item in items:
            if item.get('removed') or (not continuing and item.get('temp')):
                continue
            state = item.get('state', {})
            if continuing and (state.get('timeOffset', 0) <= 0 or state.get('duration', 0) > 0 and state.get('timeOffset', 0) >= state['duration'] * .95):
                continue
            result.append(dict(item, id=item['_id']))
        return result

    def saved(self, ident):
        item = self.state['library'].get(ident, {})
        return bool(item) and not item.get('removed') and not item.get('temp')

    def resume(self, ident, video):
        state = self.state['library'].get(ident, {}).get('state', {})
        pos = state.get('timeOffset', 0)
        return pos / 1000 if state.get('video_id') == video and not (state.get('duration', 0) and pos >= state['duration'] * .95) else 0

    def base_item(self, title):
        ident = title.get('id', title.get('_id'))
        item = json.loads(json.dumps(self.state['library'].get(ident, {'_id': ident, '_ctime': stamp(), 'state': {}, 'temp': True})))
        item.update({k: title.get(k, '') for k in ('name', 'poster', 'background')})
        item.update(type=title.get('type', 'movie'), _mtime=stamp())
        return item

    def queue(self, item):
        self.state['library'][item['_id']] = item
        self.state['pending'][item['_id']] = item
        self.persist()

    def toggle(self, title):
        with self.lock:
            item = self.base_item(title)
            item.update(removed=self.saved(item['_id']), temp=False)
            self.queue(item)
            saved = not item['removed']
            self.flush()
            return saved

    def progress(self, title, video, position, duration, watched, ended=False):
        with self.lock:
            if not self.connected or duration <= 0:
                return
            item = self.base_item(title)
            state = item.setdefault('state', {})
            if state.get('video_id') != video:
                state.update(timeWatched=0, flaggedWatched=0)
            state.update(video_id=video, timeOffset=0 if ended or position >= duration * .95 else round(position * 1000), duration=round(duration * 1000), lastWatched=stamp(), timeWatched=state.get('timeWatched', 0) + round(watched * 1000), overallTimeWatched=state.get('overallTimeWatched', 0) + round(watched * 1000))
            if (ended or state['timeWatched'] > state['duration'] * .7) and not state.get('flaggedWatched'):
                state.update(flaggedWatched=1, timesWatched=state.get('timesWatched', 0) + 1)
            item.setdefault('removed', False)
            self.queue(item)
            self.flush()

    def flush(self):
        if not self.connected:
            return
        for ident, item in list(self.state['pending'].items()):
            try:
                self.api('datastorePut', authKey=self.state['key'], collection='libraryItem', changes=[item])
                self.state['pending'].pop(ident, None)
            except Exception:
                break
        self.persist()
