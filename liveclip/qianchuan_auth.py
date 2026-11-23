"""Load the installed credential bridge and verify upload accounts before use."""
import importlib.util
import os
from pathlib import Path

DEFAULT_SERVICE = (Path(__file__).resolve().parents[1] / 'config/'
                   'local_qianchuan_service.py')
APP_ID = '9000000000000007'


def load_service(path=None):
    path = Path(path or os.environ.get('LIVECLIP_QIANCHUAN_SERVICE', DEFAULT_SERVICE)).expanduser()
    if not path.is_file():
        raise RuntimeError('qianchuan_credential_service_missing')
    spec = importlib.util.spec_from_file_location('liveclip_credential_service', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if str(getattr(module, 'APP_ID', '')) != APP_ID:
        raise RuntimeError('qianchuan_credential_application_mismatch')
    for name in ('_probe_account', '_refresh_token', '_keychain_read'):
        if not callable(getattr(module, name, None)):
            raise RuntimeError('qianchuan_credential_service_incompatible')
    if not getattr(module, 'ACCESS_SERVICE', None):
        raise RuntimeError('qianchuan_credential_service_incompatible')
    return module


def verified_token(module, accounts):
    accounts = tuple(accounts)
    if not accounts or str(module.APP_ID) != APP_ID:
        raise RuntimeError('qianchuan_credential_application_or_accounts_invalid')
    refreshed = False
    while True:
        restart = False
        for account in accounts:
            module.ACCOUNT_ID = str(account)
            result = module._probe_account()
            code = result.get('code')
            if code == 0:
                continue
            if code == 40102 and not refreshed:
                refreshed = True
                refresh = module._refresh_token()
                if refresh.get('code') != 0:
                    raise RuntimeError('qianchuan_refresh_failed_code_' + str(refresh.get('code')))
                restart = True
                break
            raise RuntimeError('qianchuan_account_probe_failed_code_' + str(code))
        if restart:
            continue
        token = module._keychain_read(module.ACCESS_SERVICE)
        if not token:
            raise RuntimeError('qianchuan_missing_token')
        return token
