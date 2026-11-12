"""Native storage routing without touching a real keyring or saved account."""
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch
import desktop_storage as storage


class DesktopStorageTests(unittest.TestCase):
    def test_macos_vault_uses_application_support(self):
        with patch.object(storage.sys, 'platform', 'darwin'), patch.object(Path, 'home', return_value=Path('/Users/fixture')):
            self.assertEqual(storage.default_vault_path(), Path('/Users/fixture/Library/Application Support/Luma TV/session.enc'))

    def test_linux_vault_preserves_xdg_location(self):
        with patch.object(storage.sys, 'platform', 'linux'), patch.dict(storage.os.environ, {'XDG_DATA_HOME': '/tmp/luma-fixture'}):
            self.assertEqual(storage.default_vault_path(), Path('/tmp/luma-fixture/luma-desktop/session.enc'))

    def test_macos_secret_uses_keychain_without_subprocess_arguments(self):
        keychain = Mock()
        keychain.get_password.return_value = 'fixture-key'
        module = types.ModuleType('keyring.backends.macOS')
        module.Keyring = Mock(return_value=keychain)
        with patch.object(storage.sys, 'platform', 'darwin'), patch.dict('sys.modules', {'keyring.backends.macOS': module}), patch.object(storage.subprocess, 'run') as process:
            self.assertEqual(storage.load_vault_key(), b'fixture-key')
            storage.store_vault_key(b'fixture-key')
            keychain.get_password.assert_called_once_with('tv.luma.desktop', 'vault')
            keychain.set_password.assert_called_once_with('tv.luma.desktop', 'vault', 'fixture-key')
            process.assert_not_called()

    def test_linux_preserves_secret_service_attributes_and_stdin(self):
        with patch.object(storage.sys, 'platform', 'linux'), patch.object(storage.subprocess, 'run') as process:
            process.return_value = types.SimpleNamespace(returncode=0, stdout=b'fixture-key\n')
            self.assertEqual(storage.load_vault_key(), b'fixture-key')
            storage.store_vault_key(b'fixture-key')
            self.assertEqual(process.call_args.kwargs['input'], b'fixture-key')
            self.assertNotIn('fixture-key', process.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
