import math
import re
from datetime import datetime, timedelta

PROMOTION_PATTERN = re.compile(
    r'优惠券|平台券|会员券|领券|折扣|凑.{0,2}单|打[一二三四五六七八九0-9]折|'
    r'放.{0,2}心.{0,2}拍|定.{0,2}心.{0,2}买|赶紧拍|抓紧拍|直接买|直接拍|下单|链接号.{0,6}身高.{0,3}体重|'
    r'(?:今天|现在|喜欢).{0,6}买一单|'
    r'[0-9一二三四五六七八九十百千零两]+多?(?:块钱|元钱)|'
    r'满\s*\d+\s*减\s*\d+|限时|截单|倒计时|'
    r'(?:(?:今天|今晚|明天|本场|现在).{0,12}(?:买得最多|卖得最多|下单|优惠|价格|上新|拍下|折扣))|'
    r'(?:到手|价格|只要|售价).{0,8}(?:\d+(?:\.\d+)?多?\s*(?:元|块)|[一二三四五六七八九十百零两]+多?[元块])'
)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Missing or invalid number')
    return value


def restore_subject(candidate, segments):
    ids=[row['id'] for row in segments]
    try:
        index=ids.index(candidate['first_id'])
    except (ValueError,KeyError):
        return candidate
    if index == 0:
        return candidate
    first=segments[index];prev=segments[index-1]
    text=first.get('text','').lstrip(' \t，。啊嗯哦哈')
    preceding=prev.get('text','').strip(' \t，。啊嗯哦哈')
    if (text.startswith(('给你们做的是','给大家做的是')) and
        re.fullmatch(r'(这|那)(一)?款\s*\d+号',preceding) and
        not prev.get('alignment_uncertain') and
        0 <= first['start']-prev['end'] <= 0.7):
        return {**candidate,'first_id':prev['id'],'boundary_adjustment':'included preceding product introduction'}
    return candidate


def validate_candidate(candidate, segments, duration):
    c = candidate
    if c.get('kind') != 'product_explanation' or c.get('complete') is not True:
        raise ValueError('Not a complete product explanation')
    if not isinstance(c.get('product'), str) or not c['product'].strip():
        raise ValueError('Unknown product')
    ids = [s['id'] for s in segments]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate segment IDs')
    try:
        first, last = ids.index(c['first_id']), ids.index(c['last_id'])
    except (ValueError, KeyError):
        raise ValueError('Invalid segment IDs') from None
    selected = segments[first:last + 1]
    if not selected:
        raise ValueError('Reversed boundaries')
    start, end = number(selected[0]['start']), number(selected[-1]['end'])
    if not 0 <= start < end <= number(duration) or not 10 <= end - start <= 30:
        raise ValueError('Invalid duration')
    previous = start
    for segment in selected:
        if segment.get('alignment_uncertain'):
            raise ValueError('Uncertain transcript alignment')
        a, b = number(segment['start']), number(segment['end'])
        if not previous <= a < b <= end:
            raise ValueError('Invalid transcript timing')
        previous = b
    text = ''.join(s['text'] for s in selected)
    if PROMOTION_PATTERN.search(text):
        raise ValueError('Promotional or time-sensitive sales content')
    if text.lstrip(' \t，。啊嗯哦哈').startswith(('给你们做的是','给大家做的是','所以','并且','而且','但是','因为','它一整件','你们去穿它')):
        raise ValueError('Clip starts mid-thought or relies on previous context')
    facts = c.get('facts', [])
    allowed = {'material', 'fit', 'construction', 'detail', 'wearing', 'use_case', 'comparison'}
    quotes = set()
    for fact in facts:
        quote = fact.get('quote')
        if fact.get('type') not in allowed or not isinstance(quote, str) or len(quote.strip()) < 3 or quote not in text:
            raise ValueError('Unsupported product evidence')
        quotes.add(quote)
    if len(quotes) < 2:
        raise ValueError('Insufficient distinct product facts')
    for field in ('information_score', 'completeness_score'):
        if not 4 <= number(c.get(field)) <= 5:
            raise ValueError('Low content quality')
    if not 0 <= number(c.get('filler_ratio')) <= .2:
        raise ValueError('Too much filler')
    return {**c, 'start': start, 'end': end, 'text': text}


def validate_visual(review):
    if review.get('matches_product') is not True or review.get('complete') is not True:
        raise ValueError('Visual content unverified')
    if not .8 <= number(review.get('product_visible_ratio')) <= 1:
        raise ValueError('Insufficient product visibility')
    if not 0 <= number(review.get('empty_ratio')) <= .15:
        raise ValueError('Empty scene')
    return review


def rank_peaks(peaks, limit=3):
    if not isinstance(limit, int) or not 1 <= limit <= 3:
        raise ValueError('At most three windows per run')
    validated = []
    for peak in peaks:
        sales = number(peak.get('sales'))
        instant = datetime.fromisoformat(peak['time'])
        if instant.tzinfo is None or sales < 0:
            raise ValueError('Require timezone and nonnegative observed sales')
        validated.append((sales, instant))
    selected = []
    for sales, instant in sorted(validated, key=lambda row: row[0], reverse=True):
        if sales == 0 or any(abs((instant - old).total_seconds()) < 360 for _, old in selected):
            continue
        selected.append((sales, instant))
        if len(selected) == limit:
            break
    return [dict(peak=t.isoformat(), sales=s, start=(t-timedelta(seconds=180)).isoformat(),
                 end=(t+timedelta(seconds=180)).isoformat()) for s, t in selected]
