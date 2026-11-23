"""Select sales spikes from a complete, observed 60-minute interval."""
from datetime import datetime,timedelta
import math


def select_hour(samples,start):
 start=datetime.fromisoformat(start)
 if start.tzinfo is None or start.second or start.microsecond:raise ValueError('Timezone-aware minute start required')
 expected={start+timedelta(minutes=i) for i in range(60)};found={}
 for sample in samples:
  t=datetime.fromisoformat(sample['time']);value=sample['sales']
  if t.tzinfo is None or t not in expected or t in found:raise ValueError('Invalid or duplicated minute')
  if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<0:raise ValueError('Invalid sales value')
  found[t]=sample
 if set(found)!=expected:raise ValueError('Incomplete hour cannot establish maximum')
 high=[found[t] for t in sorted(found) if found[t]['sales']>=1000]
 if high:return high
 best=max(sorted(found),key=lambda t:found[t]['sales'])
 return [found[best]] if found[best]['sales']>=600 else []
