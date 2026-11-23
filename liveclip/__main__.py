"""Review a downloaded window; export only after semantic and visual approval."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from .model import Client
from .policy import validate_candidate, validate_visual, restore_subject
from .prompts import SELECT, VISUAL, compact_segments
from .end_breath import choose_end, detect_gaps
from scripts.media_pipeline import probe, write_json


def valid_source_duration(duration, relative_window=False):
    return bool(duration and 358 <= duration <= (365 if relative_window else 362))


def upload_completed_review(report, output, runner=subprocess.run):
    if report.get('status') != 'complete':
        return False
    uploader = Path(__file__).resolve().parents[1] / 'scripts/upload_reviewed_library.py'
    runner([sys.executable, str(uploader), str(output / 'review_report.json')], check=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--transcript', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider', choices=['doubao', 'deepseek'], default='deepseek')
    parser.add_argument('--model')
    parser.add_argument('--asr-model', default='small')
    parser.add_argument('--asr-mode', choices=['local', 'deepseek'], default='local')
    parser.add_argument('--relative-window', action='store_true', help='Use up to 365 seconds on the source-relative timeline; absolute offset remains unverified')
    parser.add_argument('--stage-uploads', action='store_true', help='Additionally stage clips in the legacy plan queue (no plan write)')
    parser.add_argument('--no-library-upload', action='store_true', help='Skip automatic material-library upload')
    parser.add_argument('--upload-queue', type=Path, default=Path('data/upload_queue.sqlite3'))
    args = parser.parse_args()
    client = Client(args.provider, args.model)
    if not client.get_key():
        parser.exit(2, 'needs_configuration: set ' + client.key_env + ' locally\n')
    # New run directory prevents accidentally mixing old accepted clips with a failed run.
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'provider': args.provider, 'model': client.model,
              'accepted': [], 'rejected': [], 'visual_sampling': '1 frame/second; not full-frame audit'}
    script = Path(__file__).resolve().parents[1] / 'scripts/media_pipeline.py'
    try:
        duration = probe(args.source)['duration']
        if not valid_source_duration(duration, args.relative_window):
            raise ValueError('Expected a six-minute source window')
        report['time_basis'] = 'source_relative_absolute_offset_unverified' if args.relative_window else 'source_relative'
        transcript = args.transcript
        if transcript is None:
            if 'tiny' in args.asr_model and args.asr_mode == 'local':
                raise ValueError('Tiny ASR is not accepted for production selection')
            subprocess.run([sys.executable, str(script), 'transcribe', str(args.source),
                            '--output', str(args.output / 'asr'), '--model', args.asr_model], check=True)
            transcript = args.output / 'asr/transcript.json'
            if args.asr_mode == 'deepseek':
                subprocess.run([sys.executable, '-m', 'liveclip.cloud_asr', str(args.source),
                                '--local-transcript', str(transcript), '--output', str(args.output / 'cloud_asr')], check=True)
                transcript = args.output / 'cloud_asr/transcript.json'
        segments = json.loads(transcript.read_text())['segments']
        if not segments:
            raise ValueError('Empty transcript: ASR needs inspection')
        from .semantic_retry import select_valid
        decision, candidates, semantic_rejections = select_valid(client, segments, duration)
        report['rejected'].extend(semantic_rejections)
        write_json(args.output / 'semantic_review.json', decision)
        import imageio_ffmpeg
        for candidate in candidates:
            try:
                clip = validate_candidate(restore_subject(candidate, segments), segments, duration)
                last_index = next(i for i, row in enumerate(segments) if row['id'] == clip['last_id'])
                next_start = segments[last_index + 1]['start'] if last_index + 1 < len(segments) else None
                nominal_end = clip['end']
                clip['end'] = choose_end(nominal_end, detect_gaps(args.source, nominal_end, duration), duration, clip['start'], next_start)
                clip['sentence_end'] = nominal_end
                clip['end_method'] = 'quiet_gap_near_sentence_end'
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                report['rejected'].append({'candidate': candidate, 'reason': str(error)})
                continue
            if any(clip['start'] < old['end'] and old['start'] < clip['end'] for old in report['accepted']):
                report['rejected'].append({'candidate': clip, 'reason': 'Overlapping accepted clip'})
                continue
            with TemporaryDirectory() as directory:
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-ss', str(clip['start']),
                                '-i', str(args.source), '-t', str(clip['end'] - clip['start']),
                                '-vf', 'fps=1,scale=384:-2', str(Path(directory) / '%03d.jpg')],
                               check=True, capture_output=True)
                images = ['data:image/jpeg;base64,' + base64.b64encode(p.read_bytes()).decode()
                          for p in sorted(Path(directory).glob('*.jpg'))]
                if len(images) < 10:
                    raise ValueError('Insufficient visual evidence')
                visual = client.review(VISUAL + json.dumps(clip, ensure_ascii=False), images)
            try:
                clip['visual_review'] = validate_visual(visual)
            except (ValueError, TypeError):
                report['rejected'].append({'candidate': clip, 'visual_review': visual, 'reason': 'Visual gate failed'})
                continue
            report['accepted'].append(clip)
        write_json(args.output / 'selection.json', {'clips': report['accepted']})
        if report['accepted']:
            subprocess.run([sys.executable, str(script), 'render', str(args.source),
                            '--output', str(args.output / 'clips'), '--selection', str(args.output / 'selection.json')], check=True)
            report['status'] = 'complete'
        else:
            report['status'] = ('needs_transcript_review' if any(s.get('alignment_uncertain') for s in segments)
                                else 'no_qualifying_clips')
    except Exception as error:
        report['status'] = 'failed'
        # Provider response bodies and credentials are never written to reports.
        report['error_type'] = type(error).__name__
        raise
    finally:
        report['usage'] = client.usage
        write_json(args.output / 'review_report.json', report)
    if args.stage_uploads and report['status']=='complete':
        from .upload_queue import UploadQueue
        UploadQueue(args.upload_queue).stage_report(args.output / 'review_report.json', [
            ('9000000000000003','9000000000000004'), ('9000000000000001','9000000000000002')])
        print('accepted clips staged in legacy plan queue; no plan write')
    if not args.no_library_upload:
        upload_completed_review(report, args.output)
    print(report['status'])


if __name__ == '__main__':
    main()
