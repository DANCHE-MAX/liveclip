"""Review already downloaded six-minute windows without consuming platform quota."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from .job import run_windows
from .model import Client


def validate_sources(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 11:
        raise ValueError('Expected one to eleven windows')
    normalized = []
    for row in rows:
        try:
            peak = datetime.fromisoformat(row['peak'])
        except (KeyError, ValueError, TypeError):
            raise ValueError('Each window requires its observed peak time') from None
        if peak.tzinfo is None:
            raise ValueError('Peak requires timezone')
        path = Path(row['path']).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        normalized.append({**row, 'path': str(path)})
    return normalized


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--provider', choices=['doubao', 'deepseek'], default='deepseek')
    p.add_argument('--asr-model', default='small')
    p.add_argument('--asr-mode', choices=['local', 'deepseek'], default='local')
    p.add_argument('--stage-uploads', action='store_true', help='Stage accepted clips for the configured accounts')
    p.add_argument('--no-library-upload', action='store_true', help='Skip automatic material-library upload')
    p.add_argument('--all-windows', action='store_true', help='Review up to eleven verified windows, stopping on errors or uncertain timing')
    p.add_argument('--upload-queue', type=Path, default=Path('data/upload_queue.sqlite3'))
    args = p.parse_args()
    windows = validate_sources(json.loads(args.manifest.read_text(encoding='utf8'))['windows'])
    client = Client(args.provider)
    if not client.get_key():
        p.exit(2, 'needs_configuration: set ' + client.key_env + ' locally\n')
    args.output.mkdir(parents=True, exist_ok=False)
    counter = 0
    def acquire(window):
        return window['path']
    def review(source, window):
        nonlocal counter
        counter += 1
        output = args.output / ('window_%02d' % counter)
        command = [sys.executable, '-m', 'liveclip', source, '--output', str(output),
                   '--provider', args.provider, '--asr-model', args.asr_model, '--asr-mode', args.asr_mode]
        if args.stage_uploads:
            command.extend(['--stage-uploads','--upload-queue',str(args.upload_queue)])
        if args.no_library_upload:
            command.append('--no-library-upload')
        if window.get('transcript'):
            command.extend(['--transcript', window['transcript']])
        subprocess.run(command, check=True)
        return json.loads((output / 'review_report.json').read_text(encoding='utf8'))['status']
    result = run_windows(windows, acquire, review, limit=11 if args.all_windows else 3, stop_on_complete=not args.all_windows)
    (args.output / 'job_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(result['status'])
    if result['status'] == 'failed':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
