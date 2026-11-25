"""Identity-bound source decisions and invitation preparation. Never sends email.

Source decisions belong to the exact source-record set confirmed by the coach, not a
shared email. Sync may add records, but a split, missing anchor, or conflicting source
decision requires a new confirmation. The global invitation lock also covers legacy
invite creation, so prepare/approve/main-admin creation cannot race each other.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException

from autogpt.coaching.db import get_db_cursor

INVITE_LOCK = 782064190
# Same lock as people.sync_people, to keep a source snapshot stable while it is saved/read.
from autogpt.coaching.people import _LOCK_KEY as PEOPLE_LOCK


_ACTIVE_LOCK = ContextVar("invite_lock", default=None)


@contextmanager
def invitation_lock():
    active = _ACTIVE_LOCK.get()
    if active is not None:
        yield active
        return
    # Outer transaction owns the lock; nested legacy storage writes use another
    # connection while the outer lock remains held. Errors release via rollback.
    with get_db_cursor(commit=True) as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (INVITE_LOCK,))
        token = _ACTIVE_LOCK.set(cur)
        try:
            yield cur
        finally:
            _ACTIVE_LOCK.reset(token)


def _links(cur, person_id):
    cur.execute('SELECT source_table, source_key FROM person_links WHERE person_id=%s ORDER BY 1,2', (person_id,))
    return [(r['source_table'], r['source_key']) for r in cur.fetchall()]


def _fingerprint(links):
    return hashlib.sha256(json.dumps(sorted(links), separators=(',', ':')).encode()).hexdigest()


def source_state(cur, person_id):
    """Fail closed: every saved anchor must still resolve to this one person."""
    links = _links(cur, person_id)
    cur.execute('''SELECT DISTINCT d.decision_id, d.source, d.anchors FROM person_source_decisions d
        WHERE d.person_id=%s OR EXISTS (
          SELECT 1 FROM jsonb_array_elements(d.anchors) a
          JOIN person_links pl ON pl.source_table=a->>0 AND pl.source_key=a->>1
          WHERE pl.person_id=%s) ORDER BY d.decision_id DESC''', (person_id, person_id))
    rows = cur.fetchall()
    if not rows:
        return {'source': 'unset', 'revision': _fingerprint(links), 'needs_review': False}
    latest = rows[0]
    anchors = latest['anchors']
    if isinstance(anchors, str):
        anchors = json.loads(anchors)
    valid = bool(anchors) and set(map(tuple, anchors)).issubset(set(links))
    # Older decisions belonging to subsets are superseded only by a new decision
    # that explicitly captured ALL current anchors. Merged conflicting groups fail closed.
    for row in rows[1:]:
        other = row['anchors']
        if isinstance(other, str):
            other = json.loads(other)
        if (set(map(tuple, anchors)) != set(links) and row['source'] != latest['source']
                and not set(map(tuple, other)).issubset(set(map(tuple, anchors)))):
            valid = False
    return {'source': latest['source'] if valid else 'unset',
            'revision': _fingerprint(links)+':'+str(latest['decision_id']), 'needs_review': not valid}


def read_source(person_id):
    with get_db_cursor() as cur:
        return source_state(cur, person_id)


def save_source(person_id, source, revision):
    if source not in ('unset', 'tut', 'non_tut'):
        raise HTTPException(400, 'מקור לא תקין')
    with get_db_cursor(commit=True) as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (PEOPLE_LOCK,))
        links = _links(cur, person_id)
        if not links:
            raise HTTPException(404, 'האדם לא נמצא')
        if revision != source_state(cur, person_id)['revision']:
            raise HTTPException(409, 'הקישור לאדם השתנה. רענן ובדוק לפני שמירת המקור.')
        cur.execute('''INSERT INTO person_source_decisions(person_id, source, anchors)
            VALUES (%s::uuid,%s,%s::jsonb)''', (person_id, source, json.dumps(links)))
    return {'ok': True}


def existing_invitation(cur, person_id, email=None, exclude_pending=None):
    """Returns only safe status/routing, never an invite token or registration URL.

    Same-recipient records on other people are a conflict, not proof of identity.
    Even expired invitations are held for review, never silently renewed.
    """
    cur.execute('''SELECT EXISTS(SELECT 1 FROM person_links WHERE person_id=%s AND source_table='user_profiles') AS joined,
      EXISTS(SELECT 1 FROM person_identifiers i JOIN person_identifiers j ON i.kind=j.kind AND i.value=j.value
        WHERE i.person_id=%s AND i.kind='email' AND j.person_id<>i.person_id)
      OR EXISTS(SELECT 1 FROM person_identifiers WHERE kind='email' AND person_id<>%s
        AND %s IS NOT NULL AND lower(btrim(value))=%s)
      OR EXISTS(SELECT 1 FROM user_profiles u WHERE %s IS NOT NULL AND lower(btrim(u.email))=%s
        AND NOT EXISTS(SELECT 1 FROM person_links pl WHERE pl.person_id=%s
          AND pl.source_table='user_profiles' AND pl.source_key=u.user_id::text)) AS ambiguous''',
                (person_id, person_id, person_id, email, email, email, email, person_id))
    identity = cur.fetchone() or {}
    if identity.get('ambiguous'):
        return {'status': 'identity_review', 'url': '/admin'}
    if identity.get('joined'):
        return {'status': 'joined', 'url': '/admin'}
    cur.execute('''SELECT i.invite_id, i.used_at, i.expires_at,
        EXISTS(SELECT 1 FROM person_links pl WHERE pl.person_id=%s AND pl.source_table='invites'
          AND pl.source_key=i.invite_id::text) AS linked,
        (i.expires_at IS NULL OR i.expires_at>now()) AS unexpired
        FROM invites i WHERE EXISTS(SELECT 1 FROM person_links pl WHERE pl.person_id=%s
          AND pl.source_table='invites' AND pl.source_key=i.invite_id::text)
        OR (%s IS NOT NULL AND lower(btrim(i.email))=%s)''', (person_id, person_id, email, email))
    invites = cur.fetchall()
    if invites:
        if len(invites) > 1 or any(not i['linked'] for i in invites):
            return {'status': 'invite_review', 'url': '/admin'}
        i = invites[0]
        result = {'status': 'used' if i['used_at'] else 'existing' if i['unexpired'] else 'expired', 'url': '/admin'}
        if result['status'] == 'expired':
            result['url'] = '/admin/invite-renewal?person='+str(person_id)+'&invite='+str(i['invite_id'])
        return result
    cur.execute('''SELECT person_id, status FROM join_invites_pending
        WHERE status IN ('pending','sending') AND (%s IS NULL OR pending_id<>%s)
        AND (person_id=%s OR (%s IS NOT NULL AND lower(btrim(email))=%s))''',
                (exclude_pending, exclude_pending, person_id, email, email))
    pending = cur.fetchall()
    if pending:
        same = len(pending) == 1 and str(pending[0]['person_id']) == str(person_id)
        return {'status': pending[0]['status'] if same else 'invite_review',
                'url': '/admin/join-invites' if same else '/admin'}
    return None


def invitation_options(person_id):
    with get_db_cursor() as cur:
        source = source_state(cur, person_id)
        cur.execute('''SELECT d.customer_email FROM person_links pl JOIN work_order_drafts d
          ON pl.source_table='work_order_drafts' AND d.order_id::text=pl.source_key
          WHERE pl.person_id=%s ORDER BY d.created_at DESC LIMIT 1''', (person_id,))
        order = cur.fetchone() or {}
        cur.execute('''SELECT DISTINCT s.source FROM person_links pl JOIN coaching_lead_submissions s
          ON pl.source_table='coaching_lead_submissions' AND s.submission_id::text=pl.source_key
          WHERE pl.person_id=%s''', (person_id,))
        reported = [r['source'] for r in cur.fetchall() if r['source']]
        return {**source, 'order_email': (order.get('customer_email') or '').strip(),
                'reported_sources': reported, 'existing': existing_invitation(cur, person_id)}


def prepare(person_id, email, confirmed, revision):
    from autogpt.coaching.email_service import validate_recipient_address
    if not confirmed:
        raise HTTPException(400, 'יש לאשר במפורש את כתובת המייל לפני ההכנה')
    email = (email or '').strip().lower()
    try:
        validate_recipient_address(email)
    except ValueError:
        raise HTTPException(400, 'כתובת המייל לא תקינה')
    with invitation_lock():
        with get_db_cursor(commit=True) as cur:
            cur.execute('SELECT pg_advisory_xact_lock(%s)', (PEOPLE_LOCK,))
            state = source_state(cur, person_id)
            if state['revision'] != revision or state['needs_review']:
                raise HTTPException(409, 'מקור או קישור האדם דורשים בדיקה. רענן את הכרטיס.')
            cur.execute('SELECT display_name FROM people WHERE person_id=%s', (person_id,))
            person = cur.fetchone()
            if not person:
                raise HTTPException(404, 'Person not found')
            if state['source'] != 'tut':
                cur.execute('''SELECT d.customer_email FROM person_links pl JOIN work_order_drafts d
                  ON pl.source_table='work_order_drafts' AND d.order_id::text=pl.source_key
                  WHERE pl.person_id=%s ORDER BY d.created_at DESC LIMIT 1''', (person_id,))
                order = cur.fetchone() or {}
                required = (order.get('customer_email') or '').strip().lower()
                if not required:
                    raise HTTPException(400, 'אין הזמנת עבודה עם אימייל לאדם הזה')
                if email != required:
                    raise HTTPException(400, 'יש להשתמש בכתובת המייל של הזמנת העבודה')
            exists = existing_invitation(cur, person_id, email)
            if exists:
                return {'ok': True, 'created': False, 'existing': exists}
            cur.execute("SELECT value FROM person_identifiers WHERE person_id=%s AND kind='phone' ORDER BY value", (person_id,))
            phones = [r['value'] for r in cur.fetchall()]
            phone = phones[0] if len(phones) == 1 else None
            cur.execute('''INSERT INTO join_invites_pending(person_id,stable_key,name,email,phone,language,source_revision)
                VALUES (%s::uuid,%s,%s,%s,%s,'he',%s) ON CONFLICT (person_id)
                WHERE status IN ('pending','sending') DO NOTHING RETURNING pending_id''',
                        (person_id, phone or email, person['display_name'], email, phone, revision))
            created = bool(cur.fetchone())
            return {'ok': True, 'created': created, 'email': email}


def list_sources():
    # Batch all anchors once. Apply the same fail-closed rule to list badges.
    with get_db_cursor() as cur:
        cur.execute('SELECT person_id,source_table,source_key FROM person_links')
        links = cur.fetchall()
        cur.execute('SELECT decision_id,person_id,source,anchors FROM person_source_decisions ORDER BY decision_id DESC')
        decisions = cur.fetchall()
    by_person = {}
    for link in links:
        by_person.setdefault(str(link['person_id']), set()).add((link['source_table'],link['source_key']))
    result = {}
    for pid, current in by_person.items():
        candidates = []
        for d in decisions:
            anchors = d['anchors']
            if isinstance(anchors, str):
                anchors = json.loads(anchors)
            anchors = set(map(tuple, anchors))
            if str(d['person_id']) == pid or anchors & current:
                candidates.append((d['source'], anchors))
        if candidates:
            source, anchors = candidates[0]
            valid = bool(anchors) and anchors.issubset(current) and all(
                anchors == current or older_source == source or older_anchors.issubset(anchors)
                for older_source, older_anchors in candidates[1:])
            result[pid] = source if valid else 'unset'
    return result


def validate_prepared_source(cur, row):
    # Historical requests have no source revision and keep their existing workflow.
    if not row.get('source_revision'):
        return
    cur.execute('SELECT pg_advisory_xact_lock(%s)', (PEOPLE_LOCK,))
    state = source_state(cur, str(row['person_id']))
    if state['needs_review'] or state['revision'] != row['source_revision']:
        raise HTTPException(409, 'מקור או קישור האדם השתנו מאז ההכנה. יש לבדוק ולהכין מחדש.')
    if state['source'] != 'tut':
        cur.execute('''SELECT d.customer_email FROM person_links pl JOIN work_order_drafts d
          ON pl.source_table='work_order_drafts' AND d.order_id::text=pl.source_key
          WHERE pl.person_id=%s ORDER BY d.created_at DESC LIMIT 1''', (row['person_id'],))
        order = cur.fetchone() or {}
        if (order.get('customer_email') or '').strip().lower() != row['email'].strip().lower():
            raise HTTPException(409, 'כתובת הזמנת העבודה השתנתה. יש לבדוק ולהכין מחדש.')
