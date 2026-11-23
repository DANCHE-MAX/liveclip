"""Match cloud transcription to local time windows, conservatively."""
import unicodedata


def clean(text):
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith(('P', 'S')))


def verify_alignment(local, cloud_text, corrections):
    if not isinstance(cloud_text, str) or not isinstance(corrections, list):
        raise ValueError('Invalid transcription or alignment')
    if [x.get('id') for x in corrections] != [x['id'] for x in local]:
        raise ValueError('Alignment must preserve each segment in order')
    source = clean(cloud_text)
    cursor = 0
    result = []
    for row, corrected in zip(local, corrections):
        text = corrected.get('text')
        if not isinstance(text, str):
            raise ValueError('Correction must be text')
        normalized = clean(text)
        if normalized:
            pos = source.find(normalized, cursor)
            if pos < 0:
                raise ValueError('Correction not supported by cloud transcription in order')
            cursor = pos + len(normalized)
        result.append({**row, 'text': text, 'alignment_uncertain': not bool(normalized)})
    return result


def conservative_alignment(local, cloud_text, corrections):
    if not isinstance(corrections,list) or [x.get('id') for x in corrections] != [x['id'] for x in local]:
        raise ValueError('Alignment must preserve each segment in order')
    source=clean(cloud_text); cursor=0; result=[]
    for row, correction in zip(local, corrections):
        text=correction.get('text')
        if not isinstance(text,str): text=''
        normalized=clean(text)
        position=source.find(normalized,cursor) if normalized else -1
        if position<0:
            text=''
        else:
            cursor=position+len(normalized)
        result.append({**row,'text':text,'alignment_uncertain':not bool(text)})
    return result


def guard_adjacent_uncertainty(rows):
    # A missed utterance can be mistakenly assigned to its neighbour.
    uncertain={i for i,row in enumerate(rows) if row.get('alignment_uncertain')}
    guarded=[]
    for i,row in enumerate(rows):
        near=any(j in uncertain for j in (i-1,i,i+1))
        guarded.append({**row,'alignment_uncertain':near,
                        'alignment_guarded_neighbour':near and i not in uncertain})
    return guarded
