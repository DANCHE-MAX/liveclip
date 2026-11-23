"""DeepSeek ASR plus conservative alignment to local timestamped ASR.

Cloud ASR has no timestamps. The local timing is approximate and is not verified
by matching text; clips still require boundary/visual review.
"""
import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import urllib.request
import uuid

import imageio_ffmpeg
from .asr_alignment import verify_alignment, conservative_alignment, guard_adjacent_uncertainty
from .model import Client
from scripts.media_pipeline import probe, write_json


def failed_alignment(rows):
    return [{**row,'text':'','alignment_uncertain':True,'alignment_error':'repair_failed'} for row in rows]


def build_alignment_prompt(cloud_text, rows):
    return ('云端识别为权威文字，本地识别仅提供时间与粗糙参考，其中大量错字。请用云端文字替换本地错字，'
            '分配到对应时间，不要输出本地错字。逐字从云端摘录；允许漏词，不允许编词。每条必须有id，顺序一致。'
            '确实无法判断才留空。返回JSON对象：{"segments":[{"id":1,"text":"摘录"}]}。\n'
            '示例：云端“这一款是宽松版型，春秋单穿冬天叠穿”；本地片段“宽宫百姓”“称秋单专冬天疊穿”'
            '应分配“宽松版型”“春秋单穿冬天叠穿”。\n云端识别文字：'+cloud_text+'\n本地粗糙识别：'+
            json.dumps([{'id':s['id'],'start':s['start'],'end':s['end'],'text':s['text']} for s in rows],ensure_ascii=False))


def recognize(audio, client):
    boundary='----liveclip'+uuid.uuid4().hex
    content=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()+audio.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
    request=urllib.request.Request('https://api.deepseek.com/v1/tools/asr',data=content,
        headers={'Authorization':'Bearer '+client.get_key(),'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(request,timeout=120) as response:
        result=json.load(response)
    if not isinstance(result.get('text'),str) or not isinstance(result.get('duration_ms'),int):
        raise ValueError('Malformed ASR response')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--local-transcript',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--resume',action='store_true',help='Reuse saved ASR evidence after a failed alignment')
    args=parser.parse_args()
    client=Client('deepseek')
    if not client.get_key():parser.exit(2,'needs_configuration: DEEPSEEK_API_KEY\n')
    local=json.loads(args.local_transcript.read_text())['segments']
    duration=probe(args.source)['duration']
    args.output.mkdir(parents=True,exist_ok=args.resume)
    results=[]; audits=[]
    for index,start in enumerate(range(0,int(duration)+1,30)):
        if start>=duration:break
        end=min(start+30,duration)
        rows=[s for s in local if start <= (s['start']+s['end'])/2 < end]
        if not rows:continue
        audio_start=max(0,start-2);audio_end=min(duration,end+2)
        cloud_path=args.output / ('cloud_%02d.json' % index)
        with TemporaryDirectory() as d:
            wav=Path(d)/'audio.wav'
            if args.resume and cloud_path.exists():
                cloud=json.loads(cloud_path.read_text())
                if cloud.get('start')!=audio_start or cloud.get('end')!=audio_end:raise ValueError('Cached ASR window mismatch')
            else:
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss',str(audio_start),'-i',str(args.source),'-t',str(audio_end-audio_start),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],check=True)
                cloud=recognize(wav,client)
        # Persist ASR evidence before the alignment call so a later model error
        # does not erase what was actually recognized.
        write_json(args.output / ('cloud_%02d.json' % index), {'start':audio_start,'end':audio_end,**cloud})
        prompt=build_alignment_prompt(cloud['text'],rows)
        alignment_path=args.output / ('alignment_%02d.json' % index)
        reply=json.loads(alignment_path.read_text()) if args.resume and alignment_path.exists() else client.review(prompt)
        write_json(args.output / ('alignment_%02d.json' % index), reply)
        try:
            aligned=conservative_alignment(rows,cloud['text'],reply.get('segments'))
        except (ValueError, AttributeError, TypeError):
            # One bounded repair call uses the same ASR response; it must pass
            # exactly the same independent evidence and order checks.
            repair=prompt+'\n上次结果未通过逐字和ID校验，请逐项修复，无法确定填空：'+json.dumps(reply,ensure_ascii=False)
            repair_path=args.output / ('alignment_%02d_repair.json' % index)
            reply=json.loads(repair_path.read_text()) if args.resume and repair_path.exists() else client.review(repair)
            write_json(repair_path, reply)
            try:aligned=verify_alignment(rows,cloud['text'],reply.get('segments'))
            except (ValueError,AttributeError,TypeError):aligned=failed_alignment(rows)
        results.extend(aligned)
        audits.append({'chunk':index,'start':audio_start,'end':audio_end,'request_id':cloud.get('request_id'),'duration_ms':cloud['duration_ms'],
                       'uncertain':sum(bool(x['alignment_uncertain']) for x in aligned)})
        write_json(args.output/'partial.json',{'segments':results,'chunks':audits})
        print('ASR chunk',index+1,'uncertain',audits[-1]['uncertain'],flush=True)
    if len(results)!=len(local):raise ValueError('Some local segments have no aligned chunk')
    results=guard_adjacent_uncertainty(results)
    write_json(args.output/'transcript.json',{'language':'zh','segments':results,'timing_source':'local_asr_approximate','chunks':audits,'model_usage':client.usage})

if __name__=='__main__':main()
