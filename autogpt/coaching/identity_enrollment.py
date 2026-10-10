"""Enrollment transaction primitives. All callers must supply proven identities.

No email/phone resolution. No session grants from admin approval alone.
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
from uuid import UUID
from autogpt.coaching.db import get_db_cursor
from autogpt.coaching.google_oidc import OAuthRejected

class EnrollmentConflict(ValueError):
    pass

def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()

def uuid_value(value):
    return str(UUID(str(value)))

def stage_google_confirmation(user_id,subject,google_email,browser,source):
    uid=uuid_value(user_id)
    if source not in ('telegram_google_dual_proof','approved_recovery','passkey_google_dual_proof'):
        raise ValueError('Unproven enrollment source')
    if not browser or not subject or len(subject)>255:
        raise ValueError('Invalid enrollment proof')
    token=secrets.token_urlsafe(32)
    with get_db_cursor(commit=True) as cur:
        cur.execute('''INSERT INTO identity_link_confirmations
            (token_hash,browser_hash,user_id,subject,google_email,source,expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,now()+interval '10 minutes')''',
            (hashed(token),hashed(browser),uid,subject,google_email,source))
    return token

def confirm_google(token,browser):
    if not token or not browser or len(token)>128 or len(browser)>128:
        raise EnrollmentConflict('Invalid confirmation')
    with get_db_cursor(commit=True) as cur:
        cur.execute('''SELECT user_id,subject,source,google_email FROM identity_link_confirmations
            WHERE token_hash=%s AND browser_hash=%s AND expires_at>now()
            AND consumed_at IS NULL FOR UPDATE''',(hashed(token),hashed(browser)))
        intent=cur.fetchone()
        if not intent: raise EnrollmentConflict('Expired or consumed confirmation')
        # Lock profile and serialize all enrollment of a subject, including
        # absent credential rows. Unique PK still enforces cross-process races.
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(intent['subject'],))
        cur.execute('SELECT account_status FROM user_profiles WHERE user_id=%s FOR UPDATE',(intent['user_id'],))
        profile=cur.fetchone()
        if not profile or profile['account_status']!='active':
            raise EnrollmentConflict('Account not active')
        cur.execute('SELECT user_id,revoked_at FROM google_login_credentials WHERE subject=%s FOR UPDATE',(intent['subject'],))
        credential=cur.fetchone()
        if credential and (str(credential['user_id'])!=str(intent['user_id']) or credential['revoked_at'] is not None):
            raise EnrollmentConflict('Google credential already claimed; manual review required')
        if not credential:
            cur.execute('''INSERT INTO google_login_credentials(subject,user_id,verified_at,source,google_email)
                VALUES (%s,%s,now(),%s,%s)''',(intent['subject'],intent['user_id'],intent['source'],intent['google_email']))
        cur.execute('UPDATE identity_link_confirmations SET consumed_at=now() WHERE token_hash=%s',(hashed(token),))
        # No user_profiles.email/google_id/phone/history/account_status update (the address is kept on the credential, for display).
    return str(intent['user_id'])

def telegram_profile(payload):
    from autogpt.coaching.telegram_auth import verify_telegram_auth
    from autogpt.coaching.config import coaching_config
    if not verify_telegram_auth(payload,coaching_config.telegram_bot_token or ''):
        raise OAuthRejected('invalid_proof')
    # signed, fresh native Telegram Login Widget id, not a typed phone.
    tid=int(payload['id'])
    with get_db_cursor() as cur:
        cur.execute('SELECT user_id,account_status FROM user_profiles WHERE telegram_user_id=%s',(tid,))
        profile=cur.fetchone()
    if not profile or profile['account_status']!='active':
        raise EnrollmentConflict('Linked active Telegram profile required')
    return str(profile['user_id'])

def create_recovery(email,browser):
    from autogpt.coaching.email_service import validate_recipient_address
    email=email.strip().lower()
    validate_recipient_address(email)
    if not browser or len(email)>254: raise ValueError('Invalid recovery request')
    token=secrets.token_urlsafe(32); code=str(secrets.randbelow(900000)+100000)
    # Code hash keyed by high-entropy request token, not unsalted six digits.
    code_hash=hmac.new(token.encode(),code.encode(),hashlib.sha256).hexdigest()
    with get_db_cursor(commit=True) as cur:
        # Distributed destination cooldown, no profile existence lookup.
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(email,))
        cur.execute('''SELECT 1 FROM identity_recovery_requests WHERE mailbox=%s
            AND created_at>now()-interval '60 seconds' LIMIT 1''',(email,))
        if cur.fetchone(): raise EnrollmentConflict('Please wait before requesting another code')
        cur.execute('''INSERT INTO identity_recovery_requests
            (token_hash,browser_hash,mailbox,code_hash,code_expires_at,expires_at)
            VALUES (%s,%s,%s,%s,now()+interval '10 minutes',now()+interval '24 hours')''',
            (hashed(token),hashed(browser),email,code_hash))
    return token,code

def verify_recovery_mail(token,browser,code):
    if not token or not browser or not isinstance(code,str) or len(code)!=6:
        raise EnrollmentConflict('Invalid code')
    good=False
    with get_db_cursor(commit=True) as cur:
        cur.execute('''SELECT code_hash FROM identity_recovery_requests
            WHERE token_hash=%s AND browser_hash=%s AND code_expires_at>now()
            AND email_verified_at IS NULL AND attempts<5 AND denied_at IS NULL
            FOR UPDATE''',(hashed(token),hashed(browser)))
        row=cur.fetchone()
        if row:
            expected=hmac.new(token.encode(),code.encode(),hashlib.sha256).hexdigest()
            good=hmac.compare_digest(expected,row['code_hash'])
            cur.execute('''UPDATE identity_recovery_requests SET attempts=attempts+1,
                email_verified_at=CASE WHEN %s THEN now() ELSE NULL END
                WHERE token_hash=%s''',(good,hashed(token)))
    # Raise OUTSIDE transaction so failed attempt count isn't rolled back.
    if not good: raise EnrollmentConflict('Invalid or expired code')

def attach_recovery_google(token,browser,subject):
    if not token or not browser or not subject: raise EnrollmentConflict('Recovery proof unavailable')
    # Only called after fresh OIDC challenge/claims verification.
    with get_db_cursor(commit=True) as cur:
        cur.execute('''UPDATE identity_recovery_requests SET subject=%s,google_proven_at=now()
            WHERE token_hash=%s AND browser_hash=%s AND email_verified_at IS NOT NULL
            AND expires_at>now() AND approved_at IS NULL AND denied_at IS NULL
            AND (subject IS NULL OR subject=%s) RETURNING token_hash''',
            (subject,hashed(token),hashed(browser),subject))
        if not cur.fetchone(): raise EnrollmentConflict('Recovery proof unavailable')

def approve_recovery(request_hash,user_id,subject):
    uid=uuid_value(user_id)
    # Caller must be authenticated admin with CSRF/origin protection.
    with get_db_cursor(commit=True) as cur:
        cur.execute('SELECT account_status FROM user_profiles WHERE user_id=%s FOR UPDATE',(uid,))
        row=cur.fetchone()
        if not row or row['account_status']!='active': raise EnrollmentConflict('Account not active')
        cur.execute('''UPDATE identity_recovery_requests SET user_id=%s,approved_at=now(),
            approval_expires_at=now()+interval '1 hour'
            WHERE token_hash=%s AND subject=%s AND email_verified_at IS NOT NULL
            AND google_proven_at IS NOT NULL AND expires_at>now()
            AND denied_at IS NULL AND approved_at IS NULL AND consumed_at IS NULL
            RETURNING token_hash''',(uid,request_hash,subject))
        if not cur.fetchone(): raise EnrollmentConflict('Recovery approval unavailable')

def complete_recovery(token,browser,subject):
    """Bind the credential and consume the approved grant in ONE transaction.

    Requires a SECOND fresh Google proof (subject) after admin approval.
    Any failure rolls back, leaving the grant unconsumed.
    """
    if not token or not browser or not subject or len(token)>128 or len(browser)>128:
        raise EnrollmentConflict('Invalid recovery')
    with get_db_cursor(commit=True) as cur:
        cur.execute('''SELECT user_id FROM identity_recovery_requests
            WHERE token_hash=%s AND browser_hash=%s AND subject=%s
            AND approved_at IS NOT NULL AND approval_expires_at>now()
            AND denied_at IS NULL AND consumed_at IS NULL FOR UPDATE''',
            (hashed(token),hashed(browser),subject))
        grant=cur.fetchone()
        if not grant: raise EnrollmentConflict('Fresh approved recovery required')
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(subject,))
        cur.execute('SELECT account_status FROM user_profiles WHERE user_id=%s FOR UPDATE',(grant['user_id'],))
        profile=cur.fetchone()
        if not profile or profile['account_status']!='active':
            raise EnrollmentConflict('Account not active')
        cur.execute('SELECT user_id,revoked_at FROM google_login_credentials WHERE subject=%s FOR UPDATE',(subject,))
        credential=cur.fetchone()
        if credential and (str(credential['user_id'])!=str(grant['user_id']) or credential['revoked_at'] is not None):
            raise EnrollmentConflict('Google credential already claimed; manual review required')
        if not credential:
            cur.execute('''INSERT INTO google_login_credentials(subject,user_id,verified_at,source)
                VALUES (%s,%s,now(),'approved_recovery')''',(subject,grant['user_id']))
        cur.execute('UPDATE identity_recovery_requests SET consumed_at=now() WHERE token_hash=%s',(hashed(token),))
    return str(grant['user_id'])


def checked_recovery(token,browser):
    with get_db_cursor() as cur:
        cur.execute("""SELECT subject,approved_at FROM identity_recovery_requests
            WHERE token_hash=%s AND browser_hash=%s AND email_verified_at IS NOT NULL
            AND expires_at>now() AND denied_at IS NULL AND consumed_at IS NULL""",(hashed(token),hashed(browser)))
        row=cur.fetchone()
    if not row: raise EnrollmentConflict('Recovery unavailable')
    return row


def pending_recovery_for_admin():
    """Verified mailbox + Google proof, not yet decided. Exposes no history."""
    with get_db_cursor() as cur:
        cur.execute('''SELECT token_hash,mailbox,subject,google_proven_at FROM identity_recovery_requests
            WHERE email_verified_at IS NOT NULL AND google_proven_at IS NOT NULL
            AND approved_at IS NULL AND denied_at IS NULL AND consumed_at IS NULL
            AND expires_at>now() ORDER BY created_at LIMIT 50''')
        return cur.fetchall()


def deny_recovery(request_hash):
    with get_db_cursor(commit=True) as cur:
        cur.execute('''UPDATE identity_recovery_requests SET denied_at=now()
            WHERE token_hash=%s AND consumed_at IS NULL''',(request_hash,))
