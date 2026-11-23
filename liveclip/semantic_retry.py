"""One bounded semantic repair using actual validator errors, never weaker gates."""
import json
from .policy import validate_candidate, restore_subject
from .prompts import SELECT, compact_segments


def select_valid(client, segments, duration):
    prompt=SELECT+json.dumps(compact_segments(segments),ensure_ascii=False)
    audits=[]
    for attempt in range(2):
        decision=client.review(prompt);valid=[];errors=[]
        candidates=decision.get('clips')
        if not isinstance(candidates,list) or len(candidates)>6 or not decision.get('reason'):
            errors.append({'reason':'Invalid semantic review schema; require clips list <=6 and nonempty overall reason'})
        else:
            for candidate in candidates:
                try:valid.append(validate_candidate(restore_subject(candidate,segments),segments,duration))
                except (ValueError,TypeError,KeyError,AttributeError) as error:
                    detail={'candidate':candidate,'reason':str(error)}
                    by_id={s['id']:s for s in segments}
                    if isinstance(candidate,dict) and candidate.get('first_id') in by_id and candidate.get('last_id') in by_id:
                        detail['actual_duration']=by_id[candidate['last_id']]['end']-by_id[candidate['first_id']]['start']
                    errors.append(detail)
        audits.extend(dict(error,attempt=attempt+1) for error in errors)
        if valid or not errors or attempt==1:return decision,valid,audits
        prompt+='\n上次结果未通过独立校验。只修复仍有充分证据的完整候选，不降低标准，不凑数；逐字证据不可改写。错误：'+json.dumps(errors,ensure_ascii=False)

