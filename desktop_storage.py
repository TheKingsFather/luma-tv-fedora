"""Platform storage paths and native keyring access for Luma's encrypted vault."""
import os
from pathlib import Path
import subprocess
import sys


def default_vault_path():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/Luma TV/session.enc'
    return Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local/share')) / 'luma-desktop/session.enc'


def load_vault_key():
    if sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
        value = Keyring().get_password('tv.luma.desktop', 'vault')
        return value.encode('ascii') if value else b''
    result = subprocess.run(['secret-tool', 'lookup', 'application', 'tv.luma.fedora',
                             'purpose', 'vault'], capture_output=True, timeout=15)
    return result.stdout.strip() if result.returncode == 0 else b''


def store_vault_key(key):
    if sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
        Keyring().set_password('tv.luma.desktop', 'vault', key.decode('ascii'))
        return
    result = subprocess.run(['secret-tool', 'store', '--label=Luma TV Stremio connection',
                             'application', 'tv.luma.fedora', 'purpose', 'vault'],
                            input=key, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Unlock your desktop keyring and try again.')
