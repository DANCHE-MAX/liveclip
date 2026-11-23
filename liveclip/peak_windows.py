"""Group observed sales peaks into six-minute source windows."""
from datetime import datetime, timedelta
import math


def _time(text):
    t=datetime.fromisoformat(text)
    if t.tzinfo is None or t.utcoffset() is None:raise ValueError('Peak and window times require timezones')
    return t


def plan_windows(peaks, existing=()):
    if len(peaks)>11:raise ValueError('At most eleven observed peaks per run')
    rows=[]
    for p in peaks:
        value=p.get('sales'); instant=_time(p['time'])
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('Observed sale value required')
        rows.append((instant,p))
    rows.sort(key=lambda x:x[0]); output=[]; remaining=rows[:]
    for w in existing:
        if w.get('verified') is not True:continue
        a,b=_time(w['start']),_time(w['end'])
        if (b-a).total_seconds()!=360 or not w.get('path'):raise ValueError('Invalid previously verified window')
        members=[r for r in remaining if a<=r[0]<=b]
        if members:
            output.append({**w,'action':'reuse','peaks':[r[1] for r in members]});remaining=[r for r in remaining if r not in members]
    while remaining:
        first=remaining[0][0]; members=[r for r in remaining if (r[0]-first).total_seconds()<=360]
        center=first+(members[-1][0]-first)/2
        output.append({'start':(center-timedelta(minutes=3)).isoformat(),'end':(center+timedelta(minutes=3)).isoformat(),'action':'download','peaks':[r[1] for r in members]})
        remaining=remaining[len(members):]
    return output
