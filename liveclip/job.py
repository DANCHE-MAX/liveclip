"""Coordinate verified windows without mistaking failures for empty results."""


def run_windows(windows, acquire, review, limit=3, stop_on_complete=True):
    if not isinstance(limit, int) or not 1 <= limit <= 11:
        raise ValueError('Window limit must be between 1 and 11')
    result = {'status': 'no_verified_sales_peaks', 'windows': []}
    for window in windows[:limit]:
        item = {'window': window}
        result['windows'].append(item)
        try:
            item['source'] = str(acquire(window))
            status = review(item['source'], window)
            if status not in ('complete', 'no_qualifying_clips', 'needs_transcript_review'):
                raise ValueError('Unexpected review status')
            item['status'] = status
        except Exception as error:
            item['status'] = 'failed'
            item['error_type'] = type(error).__name__
            result['status'] = 'failed'
            return result
        if status == 'needs_transcript_review':
            result['status'] = status
            break
        if status == 'complete' or result['status'] != 'complete':
            result['status'] = status
        if status == 'complete' and stop_on_complete:
            break
    return result
