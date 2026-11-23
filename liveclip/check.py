"""Read-only local preflight; never prints credential values."""
import importlib.util
import json
import os
from pathlib import Path
from .model import Client

def main():
    root = Path(__file__).resolve().parent.parent
    result = {
        'deepseek_key_configured': bool(Client('deepseek').get_key()),
        'doubao_key_configured': bool(Client('doubao').get_key()),
        'faster_whisper_installed': bool(importlib.util.find_spec('faster_whisper')),
        'imageio_ffmpeg_installed': bool(importlib.util.find_spec('imageio_ffmpeg')),
        'playwright_installed': bool(importlib.util.find_spec('playwright')),
        'browser_acquisition_implemented': False,
        'existing_sources': {
            '2026-11-18 13:23-13:29': (root/'outputs/pilot_20261118_1326/source_6min.mp4').is_file(),
            '2026-11-18 15:40-15:46': (root/'outputs/pilot_20261118_1543/source_6min.mp4').is_file(),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
