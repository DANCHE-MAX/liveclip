import importlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class AuthRecoveryTests(unittest.TestCase):
    def auth(self):
        try:
            return importlib.import_module('liveclip.qianchuan_auth')
        except ModuleNotFoundError:
            self.fail('Uploader credential adapter is missing')

    def test_loads_configured_existing_service_without_old_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'service.py'
            path.write_text('APP_ID="9000000000000007"\nACCESS_SERVICE="access"\n'
                            'def _probe_account(): return {"code":0}\n'
                            'def _keychain_read(service): return "test-only"\n'
                            'def _refresh_token(): return {"code":0}\n')
            module = self.auth().load_service(path)
            self.assertEqual(self.auth().verified_token(module, ['one', 'two']), 'test-only')

    def test_expired_token_refreshes_once_and_rechecks_every_account(self):
        module = SimpleNamespace(APP_ID='9000000000000007', ACCESS_SERVICE='access', refreshed=False)
        module._probe_account = lambda: {'code': 0 if module.refreshed else 40102}
        def refresh():
            if module.refreshed:
                raise AssertionError('Repeated refresh')
            module.refreshed = True
            return {'code': 0}
        module._refresh_token = refresh
        module._keychain_read = lambda _: 'fresh' if module.refreshed else 'expired'
        self.assertEqual(self.auth().verified_token(module, ['one', 'two']), 'fresh')

    def test_failed_post_refresh_probe_blocks_token_handoff(self):
        module = SimpleNamespace(APP_ID='9000000000000007', ACCESS_SERVICE='access')
        module._probe_account = lambda: {'code': 40102}
        module._refresh_token = lambda: {'code': 0}
        module._keychain_read = lambda _: self.fail('Must not read token after failed probe')
        with self.assertRaisesRegex(RuntimeError, '40102'):
            self.auth().verified_token(module, ['one', 'two'])

    def test_non_expiry_failure_does_not_refresh(self):
        module = SimpleNamespace(APP_ID='9000000000000007', ACCESS_SERVICE='access')
        module._probe_account = lambda: {'code': 40001}
        module._refresh_token = lambda: self.fail('Must not refresh mapping/permission failures')
        with self.assertRaisesRegex(RuntimeError, '40001'):
            self.auth().verified_token(module, ['one'])

    def test_wrong_application_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'wrong.py'
            path.write_text('APP_ID="9000000000000008"\n')
            with self.assertRaisesRegex(RuntimeError, 'application'):
                self.auth().load_service(path)
