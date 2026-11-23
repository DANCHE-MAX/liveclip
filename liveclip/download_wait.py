"""Detect one newly completed browser download without accepting partial files."""
import argparse, json, time
from pathlib import Path
from .handoff import validate_download_name


def snapshot(directory):
    return sorted(p.name for p in Path(directory).iterdir() if p.is_file())


def wait_for_download(directory, before, start, end, timeout=600, poll=1, stable_checks=3):
    root=Path(directory); before=set(before); deadline=time.monotonic()+timeout
    seen=None; stable=0
    while time.monotonic()<deadline:
        candidates=[]
        for p in root.iterdir():
            if not p.is_file() or p.name in before or not p.name.lower().endswith('.mp4'): continue
            try: validate_download_name(p.name,start,end)
            except ValueError: continue
            candidates.append(p)
        if len(candidates)>1: raise ValueError('Multiple new matching downloads; cannot identify source')
        if candidates:
            p=candidates[0]
            if not (root/(p.name+'.crdownload')).exists():
                stat=p.stat(); current=(p.name,stat.st_size,stat.st_mtime_ns)
                stable=stable+1 if current==seen and stat.st_size else 1
                seen=current
                if stable>=stable_checks: return p.resolve()
        time.sleep(poll)
    raise TimeoutError('No completed matching download detected')


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('snapshot');a.add_argument('directory');a.add_argument('snapshot_file',type=Path)
    b=sub.add_parser('wait');b.add_argument('directory');b.add_argument('snapshot_file',type=Path);b.add_argument('start');b.add_argument('end');b.add_argument('--timeout',type=float,default=600)
    args=p.parse_args()
    if args.action=='snapshot':
        with args.snapshot_file.open('x',encoding='utf8') as f: json.dump(snapshot(args.directory),f,ensure_ascii=False)
        print(json.dumps({'status':'snapshot'}))
    else:
        before=json.loads(args.snapshot_file.read_text(encoding='utf8'))
        result=wait_for_download(args.directory,before,args.start,args.end,timeout=args.timeout)
        print(json.dumps({'status':'detected','path':str(result)},ensure_ascii=False))

if __name__=='__main__':main()
