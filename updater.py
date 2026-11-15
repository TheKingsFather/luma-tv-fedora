"""GitHub release updates for installed AppImages and macOS bundles.

Downloads are authenticated only to GitHub's API, verified before staging,
and installed with a rollback copy. Account data is never touched.
"""
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import requests

API = 'https://api.github.com/repos/TheKingsFather/luma-tv-fedora'

class UpdateError(Exception):
    pass

class AuthenticationRequired(UpdateError):
    pass

def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    if not match:
        raise UpdateError('The release has an unsupported version number.')
    return tuple(map(int, match.groups()))

def target():
    if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parents[2]
    image = os.environ.get('APPIMAGE')
    if sys.platform.startswith('linux') and image:
        return Path(image).resolve()
    raise UpdateError('In-app installation requires the packaged macOS app or Fedora AppImage. Download that edition from GitHub Releases first.')

def local_token():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN', '')
    cli=shutil.which('gh')
    if not cli:
        cli=next((str(p) for p in (Path.home()/'.local/bin/gh',Path('/opt/homebrew/bin/gh'),Path('/usr/local/bin/gh')) if p.is_file() and os.access(p,os.X_OK)),None)
    if not token and cli:
        result = subprocess.run([cli,'auth','token'],capture_output=True,text=True,timeout=10)
        if result.returncode == 0:token = result.stdout.strip()
    return token

def get(path, token='', binary=False):
    # Never use a server-supplied URL for an authenticated request.
    headers = {'Accept':'application/octet-stream' if binary else 'application/vnd.github+json',
               'User-Agent':'Luma-TV-Updater','X-GitHub-Api-Version':'2022-11-28'}
    if token:headers['Authorization']='Bearer '+token
    response = requests.get(API+path,headers=headers,timeout=(10,60),stream=binary)
    if response.status_code in (401,403,404):
        response.close()
        raise AuthenticationRequired('GitHub could not grant release access. This private repository needs a token with Contents: Read permission.')
    try:response.raise_for_status()
    except requests.RequestException:
        response.close();raise UpdateError('GitHub could not complete the update request. Try again later.') from None
    return response

def check(current, token=''):
    destination=target()
    with get('/releases/latest',token) as response:release=response.json()
    if release.get('draft') or release.get('prerelease') or version(release['tag_name'])<=version(current):return None
    number=release['tag_name'].removeprefix('v')
    arch={'AMD64':'x86_64','aarch64':'arm64'}.get(platform.machine(),platform.machine())
    name=f'Luma-TV-{number}-macOS-{arch}.dmg' if sys.platform=='darwin' else f'Luma-TV-{number}-{arch}.AppImage'
    asset=next((a for a in release.get('assets',[]) if a['name']==name),None)
    if not asset:raise UpdateError('This release has no package for your operating system and processor.')
    digest=asset.get('digest','')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise UpdateError('This release is missing a verified SHA-256 digest.')
    return dict(version=number,asset=asset,target=destination,digest=digest[7:])

def stage(update, token=''):
    destination=update['target']
    if not os.access(destination.parent,os.W_OK):raise UpdateError('Move Luma to a writable Applications folder or AppImage location before updating.')
    folder=Path(tempfile.mkdtemp(prefix='.luma-update-',dir=destination.parent))
    package=folder/update['asset']['name']
    try:
        digest=hashlib.sha256();size=0
        with get('/releases/assets/'+str(int(update['asset']['id'])),token,True) as response, package.open('wb') as output:
            for chunk in response.iter_content(1024*1024):
                size+=len(chunk)
                if size>update['asset']['size']:raise UpdateError('The download exceeds its published size.')
                digest.update(chunk);output.write(chunk)
        if size!=update['asset']['size'] or digest.hexdigest()!=update['digest']:raise UpdateError('The update failed its integrity check. Your installation is unchanged.')
        if destination.suffix=='.app':
            mount=folder/'mounted';mount.mkdir()
            subprocess.run(['/usr/bin/hdiutil','attach',str(package),'-readonly','-nobrowse','-mountpoint',str(mount)],check=True,capture_output=True,timeout=60)
            try:
                staged=folder/'Luma TV.app'
                subprocess.run(['/usr/bin/ditto',str(mount/'Luma TV.app'),str(staged)],check=True,capture_output=True,timeout=120)
                subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(staged)],check=True,capture_output=True,timeout=60)
            finally:subprocess.run(['/usr/bin/hdiutil','detach',str(mount)],check=True,capture_output=True,timeout=60)
        else:
            staged=package;staged.chmod(0o755)
        return folder,staged
    except Exception:
        shutil.rmtree(folder,ignore_errors=True);raise

def install(destination, staged):
    """Swap only verified staged packages, restoring the original on failure."""
    backup=destination.with_name(destination.name+'.previous')
    if backup.exists():
        if backup.is_dir():shutil.rmtree(backup)
        else:backup.unlink()
    destination.rename(backup)
    try:staged.rename(destination)
    except OSError:
        backup.rename(destination);raise
    return backup

def restart(destination):
    # Wait for the old process to finish its account writes and Qt teardown.
    command='while kill -0 "$1" 2>/dev/null; do sleep 1; done; '
    command+='exec /usr/bin/open -n "$2"' if destination.suffix=='.app' else 'exec "$2"'
    subprocess.Popen(['/bin/sh','-c',command,'luma-restart',str(os.getpid()),str(destination)],
                     start_new_session=True,close_fds=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
