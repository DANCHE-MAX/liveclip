"""Parsing and payload construction for the documented EBP video-tag API.

No network call is made here. Production use requires explicit authorization,
preflight, account/material mapping, and a verified readback.
"""

WORKBENCH_ID = 9000000000000006
LABEL = '切片'


def tag_status(response, material_id):
    """Return true/false only for an unambiguous successful material result."""
    if not isinstance(response, dict) or response.get('code') != 0:
        return None
    data = response.get('data')
    if not isinstance(data, dict):
        return None
    if 'data' in data and isinstance(data['data'], dict):
        data = data['data']
    errors = data.get('errors', [])
    materials = data.get('materials')
    if not isinstance(errors, list) or not isinstance(materials, list):
        return None
    if any(not isinstance(e, dict) or 'material_id' not in e for e in errors):
        return None
    if any(str(e.get('material_id')) == str(material_id) for e in errors if isinstance(e, dict)):
        return None
    matched = [x for x in materials if isinstance(x, dict) and str(x.get('material_id')) == str(material_id)]
    if len(matched) != 1 or not isinstance(matched[0].get('tags'), list):
        return None
    tags = matched[0]['tags']
    if any(not isinstance(t, dict) or 'tag_name' not in t or 'tag_type' not in t for t in tags):
        return None
    return any(t['tag_name'] == LABEL and t['tag_type'] == 'CUSTOM' for t in tags)


def build_add_payload(account_id, material_id):
    if account_id != WORKBENCH_ID or isinstance(material_id, bool) or not isinstance(material_id, int) or material_id <= 0:
        raise ValueError('An approved workbench and valid material ID are required')
    return {'account_id': account_id, 'account_type': 'EBP', 'material_ids': [material_id],
            'action': 'ADD', 'custom_tag_names': [LABEL]}
