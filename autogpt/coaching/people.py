"""People: one person per phone number or email across questionnaire, bookings, work orders, invites and users.

Matching rules (same as the funnel spec):
  a. the same E.164 phone is the same person;
  b. the same email is the same person, unless both sides already have different phones;
  c. one phone with different emails stays one person, the emails are all kept;
  d. the same email on people with different phones is never merged. It is listed for a manual look;
  e. a name alone never merges anyone.
compute_people() is pure. sync_people() reads the source tables and writes only people, person_identifiers,
person_links and people_review, in one transaction. Existing tables are never written.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Iterable, Optional

from autogpt.coaching.db import get_db_cursor
from autogpt.coaching.phone import normalize_phone

logger = logging.getLogger(__name__)

SUBMISSIONS = "coaching_lead_submissions"
BOOKINGS = "booking_notifications"
ORDERS = "work_order_drafts"
INVITES = "invites"
USERS = "user_profiles"
# Which source gives the display name first.
NAME_PRIORITY = (USERS, ORDERS, SUBMISSIONS, BOOKINGS, INVITES)
_NAMESPACE = uuid.UUID("5f0c2d8e-3a1b-4c55-9d27-6b1e0f4a7c10")
_LOCK_KEY = 7420261004


@dataclass(frozen=True)
class Rec:
    table: str
    key: str
    name: str = ""
    phones: tuple = ()
    emails: tuple = ()


@dataclass
class Person:
    person_id: str
    display_name: str
    phones: list = field(default_factory=list)
    emails: list = field(default_factory=list)
    links: list = field(default_factory=list)  # (source_table, source_key)
    sources: dict = field(default_factory=dict)  # (kind, value) -> first source table


@dataclass
class Review:
    kind: str
    value: str
    person_ids: list


def clean_email(value) -> str:
    text = str(value or "").strip().lower()
    return text if "@" in text and " " not in text else ""


def make_rec(table, key, name, phones: Iterable, emails: Iterable) -> Optional[Rec]:
    """None when the record has neither a usable phone nor an email: it cannot be placed."""
    ph = sorted({p for p in (normalize_phone(x) for x in phones if x) if p})
    em = sorted({e for e in (clean_email(x) for x in emails if x) if e})
    if not ph and not em:
        return None
    return Rec(table, str(key), str(name or "").strip(), tuple(ph), tuple(em))


class _Sets:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # smallest id is the root: stable result


def compute_people(records: list, existing: Optional[dict] = None):
    """Return (people, review). existing maps (source_table, source_key) -> person_id to keep ids stable."""
    existing = existing or {}
    recs = {(r.table, r.key): r for r in records}
    ids = sorted(recs)
    sets = _Sets(ids)

    by_phone: dict = {}
    for i in ids:
        for p in recs[i].phones:
            by_phone.setdefault(p, []).append(i)
    for members in by_phone.values():
        for m in members[1:]:
            sets.union(members[0], m)

    by_email: dict = {}
    for i in ids:
        for e in recs[i].emails:
            by_email.setdefault(e, []).append(i)

    def comp_phones(root):
        return {p for i in ids if sets.find(i) == root for p in recs[i].phones}

    for email in sorted(by_email):
        roots = sorted({sets.find(i) for i in by_email[email]})
        with_phone = [r for r in roots if comp_phones(r)]
        if len(with_phone) <= 1:
            for r in roots[1:]:
                sets.union(roots[0], r)

    groups: dict = {}
    for i in ids:
        groups.setdefault(sets.find(i), []).append(i)

    people, root_to_id, used = [], {}, set()
    for root in sorted(groups):
        members = groups[root]
        kept = sorted({str(existing[m]) for m in members if m in existing} - used)
        pid = kept[0] if kept else str(uuid.uuid5(_NAMESPACE, "%s:%s" % members[0]))
        used.add(pid)
        root_to_id[root] = pid
        person = Person(person_id=pid, display_name="", links=list(members))
        for m in members:
            r = recs[m]
            for p in r.phones:
                person.sources.setdefault(("phone", p), r.table)
            for e in r.emails:
                person.sources.setdefault(("email", e), r.table)
        person.phones = sorted(v for k, v in person.sources if k == "phone")
        person.emails = sorted(v for k, v in person.sources if k == "email")
        named = sorted((NAME_PRIORITY.index(recs[m].table), m[1], recs[m].name) for m in members if recs[m].name)
        person.display_name = named[0][2] if named else ""
        people.append(person)

    review = []
    for email in sorted(by_email):
        roots = sorted({sets.find(i) for i in by_email[email]})
        with_phone = [r for r in roots if comp_phones(r)]
        if len(with_phone) >= 2:
            review.append(Review("email_multiple_phones", email, sorted(root_to_id[r] for r in with_phone)))
    return people, review


def load_records(cur) -> list:
    """Read the five sources. Reads only."""
    out = []

    def add(rec):
        if rec:
            out.append(rec)

    cur.execute("""SELECT l.submission_id, COALESCE(c.name, l.name) AS name, l.email, c.email AS contact_email,
        l.phone_e164, c.mobile_phone FROM coaching_lead_submissions l
        LEFT JOIN coaching_lead_contacts c USING (submission_id)""")
    for r in cur.fetchall():
        add(make_rec(SUBMISSIONS, r["submission_id"], r["name"], [r["phone_e164"], r["mobile_phone"]],
                     [r["email"], r["contact_email"]]))
    cur.execute("SELECT event_id, payload FROM booking_notifications")
    for r in cur.fetchall():
        p = r["payload"] or {}
        add(make_rec(BOOKINGS, r["event_id"], p.get("name"), [p.get("phone")], [p.get("email")]))
    cur.execute("SELECT order_id, customer_name, customer_email, customer_phone FROM work_order_drafts")
    for r in cur.fetchall():
        add(make_rec(ORDERS, r["order_id"], r["customer_name"], [r["customer_phone"]], [r["customer_email"]]))
    cur.execute("SELECT invite_id, name, email, phone FROM invites")
    for r in cur.fetchall():
        add(make_rec(INVITES, r["invite_id"], r["name"], [r["phone"]], [r["email"]]))
    cur.execute("SELECT user_id, name, email, phone_number FROM user_profiles")
    for r in cur.fetchall():
        add(make_rec(USERS, r["user_id"], r["name"], [r["phone_number"]], [r["email"]]))
    return out


def sync_people() -> dict:
    """Rebuild people from the sources. Idempotent. Writes only the four people tables."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        records = load_records(cur)
        cur.execute("SELECT source_table, source_key, person_id FROM person_links")
        existing = {(r["source_table"], r["source_key"]): r["person_id"] for r in cur.fetchall()}
        people, review = compute_people(records, existing)
        keep = [p.person_id for p in people]
        cur.execute("DELETE FROM people_review")
        cur.execute("DELETE FROM person_links")
        cur.execute("DELETE FROM person_identifiers")
        cur.execute("DELETE FROM people WHERE NOT (person_id = ANY(%s::uuid[]))", (keep,))
        for p in people:
            cur.execute("""INSERT INTO people(person_id, display_name) VALUES (%s, %s)
                ON CONFLICT (person_id) DO UPDATE SET display_name = excluded.display_name, updated_at = now()""",
                        (p.person_id, p.display_name))
            for (kind, value), source in sorted(p.sources.items()):
                cur.execute("INSERT INTO person_identifiers(person_id, kind, value, source) VALUES (%s, %s, %s, %s)",
                            (p.person_id, kind, value, source))
            for table, key in p.links:
                cur.execute("INSERT INTO person_links(person_id, source_table, source_key) VALUES (%s, %s, %s)",
                            (p.person_id, table, key))
        for r in review:
            cur.execute("INSERT INTO people_review(kind, value, person_ids) VALUES (%s, %s, %s::uuid[])",
                        (r.kind, r.value, r.person_ids))
    logger.info("People synced: %d people, %d to review, %d records", len(people), len(review), len(records))
    return {"people": len(people), "review": len(review), "records": len(records)}
