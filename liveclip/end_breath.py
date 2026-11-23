"""Find a quiet cut after a sentence, bounded by the next transcript segment."""
import math
import re
import subprocess


def choose_end(sentence_end, gaps, source_duration, clip_start, next_start=None):
 values=(sentence_end,source_duration,clip_start)
 if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):raise ValueError('Invalid timing')
 limit=min(source_duration,clip_start+30, next_start-0.05 if next_start is not None else source_duration)
 target=min(sentence_end+0.5,limit)
 options=[]
 for a,b in gaps:
  if b-a<0.12 or a>sentence_end+0.35:continue
  lo=max(a,sentence_end);hi=min(b-0.03,limit)
  if hi>=lo:options.append(max(lo,min(target,hi)))
 if not options:raise ValueError('No safe quiet boundary after sentence')
 return min(options,key=lambda x:abs(x-target))


def detect_gaps(source,sentence_end,source_duration):
 import imageio_ffmpeg
 begin=max(0,sentence_end-0.5);length=min(2.5,source_duration-begin)
 result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-nostats','-ss',str(begin),'-t',str(length),'-i',str(source),'-vn','-af','silencedetect=noise=-35dB:d=0.12','-f','null','-'],capture_output=True,text=True,check=True)
 starts=[float(x) for x in re.findall(r'silence_start:\s*([\d.]+)',result.stderr)]
 ends=[float(x) for x in re.findall(r'silence_end:\s*([\d.]+)',result.stderr)]
 return [(begin+a,begin+b) for a,b in zip(starts,ends) if b>a]
