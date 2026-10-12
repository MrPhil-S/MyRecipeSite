"""Signed per-row previews; no database mutation occurs here."""
import base64
import hashlib
import hmac
import json
import time


def sign_preview(recipe_id, row_id, name, version, catalogue_version, target):
    from .editor_routes import SECRET
    payload = {'recipe': recipe_id, 'row': row_id, 'name': name, 'version': version,
               'catalogue': catalogue_version, 'target': target, 'time': int(time.time())}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
    signature = hmac.new(SECRET, ('ingredient-image:' + encoded).encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


def read_preview(token):
    from .editor_routes import SECRET
    try:
        if len(token) > 2048:
            raise ValueError()
        encoded, signature = token.rsplit('.', 1)
        expected = hmac.new(SECRET, ('ingredient-image:' + encoded).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded))
        if not 0 <= time.time() - payload['time'] <= 7200:
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError):
        raise ValueError('Re-match this ingredient again before saving.') from None


def verify_preview(token, recipe_id, row_id, name, version, catalogue_version):
    payload = read_preview(token)
    expected = {'recipe': recipe_id, 'row': row_id, 'name': name, 'version': version,
                'catalogue': catalogue_version}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError('This ingredient or the alias catalogue changed. Re-match it again before saving.')
    return payload['target']
