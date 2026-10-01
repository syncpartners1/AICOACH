"""Durable coach inbox. A saved message is acknowledged only after commit."""
from __future__ import annotations

import uuid
from html import escape
from urllib.parse import quote
from zoneinfo import ZoneInfo

from autogpt.coaching.db import get_db_cursor

PAGE_SIZE = 30


def save_message(*, user_id, sender_name, sender_id, chat_id, source_message_id, body):
    body = body.strip()
    if not 1 <= len(body) <= 4096:
        raise ValueError("Message must contain 1-4096 characters")
    # Cursor context commits before this function returns. Retry keys are scoped
    # to the source chat because Telegram message IDs are not globally unique.
    with get_db_cursor(commit=True) as cur:
        cur.execute("""INSERT INTO coach_messages
            (message_id,user_id,sender_name,channel,telegram_sender_id,
             telegram_chat_id,telegram_message_id,body)
            VALUES (%s,%s,%s,'telegram',%s,%s,%s,%s)
            ON CONFLICT (channel,telegram_chat_id,telegram_message_id) DO NOTHING
            RETURNING message_id""",
            (str(uuid.uuid4()), user_id, sender_name, sender_id, chat_id, source_message_id, body))
        row = cur.fetchone()
        if row is None:
            cur.execute("""SELECT message_id,user_id,telegram_sender_id,body FROM coach_messages
                WHERE channel='telegram' AND telegram_chat_id=%s AND telegram_message_id=%s""",
                (chat_id, source_message_id))
            row = cur.fetchone()
            if (not row or str(row['user_id']) != str(user_id)
                    or row['telegram_sender_id'] != sender_id or row['body'] != body):
                raise ValueError("Source message identity conflict")
        message_id = str(row['message_id'])
    return message_id


def unread_count():
    with get_db_cursor() as cur:
        cur.execute("SELECT count(*) AS count FROM coach_messages WHERE read_at IS NULL")
        return int(cur.fetchone()['count'])


def list_messages(page=1):
    if not 1 <= page <= 10000:
        raise ValueError("Invalid page")
    with get_db_cursor() as cur:
        cur.execute("""SELECT message_id,user_id,sender_name,channel,body,created_at,read_at
            FROM coach_messages ORDER BY created_at DESC,message_id DESC LIMIT %s OFFSET %s""",
            (PAGE_SIZE + 1, (page - 1) * PAGE_SIZE))
        rows = [dict(row) for row in cur.fetchall()]
    return rows[:PAGE_SIZE], len(rows) > PAGE_SIZE


def mark_read(message_id):
    with get_db_cursor(commit=True) as cur:
        cur.execute("""UPDATE coach_messages SET read_at=COALESCE(read_at,now())
            WHERE message_id=%s RETURNING message_id""", (str(message_id),))
        found = cur.fetchone() is not None
    return found


def render_inbox(rows, unread, page=1, has_next=False, error=False):
    cards = []
    for row in rows:
        mid = str(uuid.UUID(str(row['message_id'])))
        user_link = '/dashboard/' + quote(str(row['user_id']), safe='') + '?lang=he'
        created = row['created_at'].astimezone(ZoneInfo('Asia/Jerusalem')).strftime('%d/%m/%Y %H:%M')
        is_unread = row['read_at'] is None
        button = (f'<button type="button" data-message-id="{mid}" onclick="markRead(this)">סימון כנקרא</button>'
                  if is_unread else '<span class="read">נקראה</span>')
        cards.append(f'''<article class="message {'unread' if is_unread else ''}">
          <div class="meta"><a href="{user_link}">{escape(row['sender_name'])}</a>
          <time>{created} · טלגרם</time><span class="badge">{'חדשה' if is_unread else 'נקראה'}</span></div>
          <div class="body">{escape(row['body'])}</div><div class="actions">{button}</div></article>''')
    content = ''.join(cards) or '<p class="empty">אין הודעות בתיבה.</p>'
    if error:
        content = '<p class="error" role="alert">לא ניתן לטעון את תיבת ההודעות כרגע. נסו שוב. אין להסיק שאין הודעות.</p>'
    prev_link = f'<a href="?page={page-1}">הקודם</a>' if page > 1 else ''
    next_link = f'<a href="?page={page+1}">הבא</a>' if has_next else ''
    count = 'לא זמין' if error else str(unread)
    return '''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>הודעות למאמן | Change Navigator</title>
    <style>body{margin:0;background:#f3f4f6;color:#1a2b4a;font-family:Arial,sans-serif}
    main{max-width:900px;margin:32px auto;padding:0 18px}h1{font-size:28px;margin-bottom:10px}
    a{color:#1d4ed8}header{margin-bottom:24px}.message{background:white;border:1px solid #d1d5db;
    border-radius:12px;padding:20px;margin:16px 0}.unread{border-right:5px solid #2563eb}
    .meta{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.meta a{font-weight:bold}
    time,.read{color:#4b5563;font-size:14px}.badge{font-size:12px;background:#e0e7ff;padding:4px 9px;border-radius:12px}
    .body{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65;margin:20px 0;color:#111827;unicode-bidi:plaintext}
    button{font:inherit;background:#1a2b4a;color:white;border:0;border-radius:7px;padding:9px 16px;cursor:pointer}
    button:disabled{opacity:.6}.error{background:#fee2e2;color:#991b1b;padding:18px;border-radius:8px}
    nav{display:flex;gap:24px;margin:24px 0}.empty{padding:24px;background:white;border-radius:10px}
    @media(max-width:500px){main{margin-top:20px}.message{padding:16px}h1{font-size:24px}}</style></head><body><main>
    <header><a href="/admin?lang=he">חזרה למסך האדמין</a><h1>הודעות למאמן</h1>''' + f'''
    <p>לא נקראו: {count}. ניתן לחזור למתאמנים מחוץ למערכת.</p></header>
    <p id="action-error" class="error" role="alert" hidden></p>{content}
    <nav>{prev_link}<span>עמוד {page}</span>{next_link}</nav>''' + '''
    <script>async function markRead(button){
      button.disabled=true; const error=document.getElementById('action-error'); error.hidden=true;
      try {const res=await fetch('/admin/messages/'+button.dataset.messageId+'/read',{
        method:'POST',headers:{'X-Inbox-Action':'mark-read'}});
        if(!res.ok)throw new Error('failed'); location.reload();
      }catch(e){error.textContent='הסימון לא נשמר. נסו שוב.';error.hidden=false;button.disabled=false;}
    }</script></main></body></html>'''
