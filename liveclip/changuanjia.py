"""Validate observed UI content; this module does not control the browser."""
import re
from datetime import datetime

ENDED = re.compile(r'(?m)^\s*(\d+) link [^\n]*Value: changuanjia\.com/analyse/(\d+)\s*\n\s*\d+ 文本 (\d{4}/\d{2}/\d{2} \d{2}:\d{2})\s*$')


def pick_latest_ended_stream(accessibility_tree):
    matches=[]
    for match in ENDED.finditer(accessibility_tree):
        try:
            start=datetime.strptime(match.group(3),'%Y/%m/%d %H:%M')
        except ValueError:
            continue
        matches.append({'element_id':int(match.group(1)),'stream_id':match.group(2),'start':start})
    if not matches:
        raise ValueError('No dated ended livestreams observed')
    return max(matches,key=lambda x:x['start'])
