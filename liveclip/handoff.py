"""Validate a downloaded, already-observed sales window for local review."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def validate_window(peak, start, end, media_duration, relative_window=False):
    times = [datetime.fromisoformat(value) for value in (peak, start, end)]
    if any(t.tzinfo is None or t.utcoffset() is None for t in times):
        raise ValueError('All window timestamps require a timezone')
    peak, start, end = [t.astimezone(timezone.utc) for t in times]
    if (peak-start).total_seconds() != 180 or (end-peak).total_seconds() != 180:
        raise ValueError('Window must be centered on the observed peak')
    if media_duration is None or not 358 <= media_duration <= (365 if relative_window else 362):
        raise ValueError('Downloaded media is not approximately six minutes')
    return {'window_seconds': 360, 'media_duration': media_duration,
            'timing_mode': 'relative_media_only' if relative_window else 'nominal_window'}


def validate_download_name(name, start, end):
    start_time, end_time = (datetime.fromisoformat(t) for t in (start, end))
    token = start_time.strftime('%Y-%m-%d %H_%M-') + end_time.strftime('%H_%M')
    if token not in name or not name.lower().endswith('.mp4'):
        raise ValueError('Download filename does not match the selected time window')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--peak', required=True)
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--stream-id', required=True)
    p.add_argument('--peak-evidence', required=True, help='Observed peak evidence, not inferred from a 5-minute aggregate')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--registry', type=Path, help='Optional download registry path')
    args = p.parse_args()
    from scripts.media_pipeline import probe
    source = args.source.expanduser().resolve(strict=True)
    validate_download_name(source.name, args.start, args.end)
    media = probe(source)
    window = validate_window(args.peak, args.start, args.end, media['duration'])
    if not {'video', 'audio'}.issubset({s['type'] for s in media['streams']}):
        raise ValueError('Downloaded media must contain video and audio')
    digest = hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            digest.update(block)
    from .download_registry import DownloadRegistry
    registry = DownloadRegistry(args.registry) if args.registry else DownloadRegistry()
    registry.register_existing(args.stream_id, args.peak, source)
    result = {'windows': [{'path': str(source), 'peak': args.peak, 'start': args.start, 'end': args.end,
                           'stream_id': args.stream_id, 'peak_evidence': args.peak_evidence,
                           'sha256': digest.hexdigest(), **window, 'media': media}]}
    with args.output.open('x', encoding='utf8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print('validated:', args.output)

if __name__ == '__main__':
    main()
