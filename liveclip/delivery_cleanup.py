"""Fail-closed cleanup of a verified batch's generated clips and archive only."""
import hashlib
import json
from pathlib import Path
import zipfile


def cleanup_completed_batch(batch_root,archive,confirmed_uploads,delivery_status,expected_accounts):
 root=Path(batch_root).resolve(strict=True);bundle=Path(archive).resolve(strict=True)
 if not bundle.is_relative_to(root) or delivery_status!='sent' or len(expected_accounts)!=2 or len(set(expected_accounts))!=2:return 'blocked'
 try:
  with zipfile.ZipFile(bundle) as z:
   if z.testzip() is not None:return 'blocked'
   manifest=json.loads(z.read('manifest.json'));items=manifest['clips']
   if not isinstance(items,list) or not items:return 'blocked'
   paths=[];seen=set()
   for item in items:
    p=Path(item['source'])
    if p.is_symlink():return 'blocked'
    p=p.resolve(strict=True);digest=item['sha256'];name=item['name']
    if not p.is_relative_to(root) or p==bundle or p in seen or not p.is_file():return 'blocked'
    if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:return 'blocked'
    if hashlib.sha256(z.read(name)).hexdigest()!=digest:return 'blocked'
    if any(digest not in confirmed_uploads.get(a,set()) for a in expected_accounts):return 'blocked'
    paths.append(p);seen.add(p)
 except (OSError,KeyError,ValueError,TypeError,zipfile.BadZipFile):return 'blocked'
 for path in paths:path.unlink()
 bundle.unlink()
 return 'complete'
