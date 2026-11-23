"""Stage local clips for later review; never contacts an advertising platform."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

ACCOUNTS = ('9000000000000003', '9000000000000001')
LABEL = '切片'
DEFAULT_DB = Path('data/material_staging.sqlite3')


class MaterialStaging:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS material_tasks (
                id INTEGER PRIMARY KEY, account TEXT NOT NULL, path TEXT NOT NULL,
                sha256 TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL,
                UNIQUE(account,sha256,label))''')

    def stage(self, paths):
        if not paths:
            raise ValueError('At least one video is required')
        files = []
        for path in paths:
            p = Path(path).resolve(strict=True)
            if not p.is_file() or p.suffix.lower() != '.mp4' or p.stat().st_size == 0:
                raise ValueError('Expected a nonempty MP4 file')
            digest = hashlib.sha256()
            with p.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            files.append((str(p), digest.hexdigest()))
        with sqlite3.connect(self.path) as db:
            for account in ACCOUNTS:
                for path, digest in files:
                    db.execute('''INSERT OR IGNORE INTO material_tasks
                        (account,path,sha256,label,status) VALUES (?,?,?,?,?)''',
                        (account, path, digest, LABEL, 'pending_review'))

    def list_tasks(self):
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                'SELECT id,account,path,sha256,label,status FROM material_tasks ORDER BY id')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('videos', nargs='+', type=Path)
    args = parser.parse_args()
    queue = MaterialStaging(args.db)
    queue.stage(args.videos)
    print(json.dumps({'status': 'pending_review', 'tag': LABEL,
                      'tasks': queue.list_tasks(), 'uploaded': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
