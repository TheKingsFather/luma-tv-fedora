"""Update integrity, platform selection and rollback without network access."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import updater

def response(value):
    result=Mock();result.__enter__=Mock(return_value=result);result.__exit__=Mock(return_value=False);result.json.return_value=value
    return result
class UpdateTests(unittest.TestCase):
    def test_new_matching_stable_release_and_digest_required(self):
        asset=dict(name='Luma-TV-0.7.0-x86_64.AppImage',id=1,size=3,digest='sha256:'+'a'*64)
        release=dict(tag_name='v0.7.0',assets=[asset])
        with patch('updater.target',return_value=Path('/tmp/luma.AppImage')),patch('updater.sys.platform','linux'),patch('updater.platform.machine',return_value='x86_64'),patch('updater.get',return_value=response(release)):
            self.assertEqual(updater.check('0.6.0')['asset'],asset)
            self.assertIsNone(updater.check('0.7.0'))
            self.assertIsNone(updater.check('0.8.0'))
            asset['digest']=''
            with self.assertRaises(updater.UpdateError):updater.check('0.6.0')
    def test_corrupt_download_leaves_installation_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'Luma.AppImage';target.write_bytes(b'old')
            update=dict(target=target,asset=dict(name='new.AppImage',id=1,size=3),digest=hashlib.sha256(b'new').hexdigest())
            download=response(None);download.iter_content.return_value=[b'bad']
            with patch('updater.get',return_value=download):
                with self.assertRaises(updater.UpdateError):updater.stage(update)
            self.assertEqual(target.read_bytes(),b'old');self.assertEqual(list(Path(tmp).iterdir()),[target])
    def test_successful_stage_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'Luma.AppImage';target.write_bytes(b'old')
            update=dict(target=target,asset=dict(name='new.AppImage',id=1,size=3),digest=hashlib.sha256(b'new').hexdigest())
            download=response(None);download.iter_content.return_value=[b'new']
            with patch('updater.get',return_value=download):folder,staged=updater.stage(update)
            backup=updater.install(target,staged)
            self.assertEqual(target.read_bytes(),b'new');self.assertEqual(backup.read_bytes(),b'old')
    def test_failed_swap_restores_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'Luma.AppImage';target.write_bytes(b'old')
            with self.assertRaises(OSError):updater.install(target,Path(tmp)/'missing')
            self.assertEqual(target.read_bytes(),b'old')
    def test_private_repo_access_has_actionable_error(self):
        with patch('updater.requests.get',return_value=Mock(status_code=404)):
            with self.assertRaises(updater.AuthenticationRequired):updater.get('/releases/latest')
    def test_credentials_only_sent_to_fixed_api(self):
        result=Mock(status_code=200)
        with patch('updater.requests.get',return_value=result) as get:
            updater.get('/releases/assets/12','session-token',True)
            self.assertEqual(get.call_args.args[0],updater.API+'/releases/assets/12')
            self.assertEqual(get.call_args.kwargs['headers']['Authorization'],'Bearer session-token')
