#!/usr/bin/env python3
"""Store the marketing app secret in a separate macOS Keychain entry."""
import getpass
import subprocess
import sys

secret = getpass.getpass('请输入新应用的 App Secret（不会显示）：').strip()
if not secret:
    sys.exit('未输入密钥，未保存。')
result = subprocess.run(['security', 'add-generic-password', '-U', '-s',
                         'liveclip-example-tags-app-secret', '-a', '9000000000000008',
                         '-w', secret], capture_output=True, text=True)
if result.returncode:
    sys.exit('钥匙串保存失败，请检查钥匙串权限。')
print('已保存到此应用的独立钥匙串条目。')
