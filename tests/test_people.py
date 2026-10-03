"""People matching and sync: pure rules, idempotence, and writes only to the four new tables."""
import re
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from autogpt.coaching import people as pp
from autogpt.coaching.people import (BOOKINGS, INVITES, ORDERS, SUBMISSIONS, USERS, compute_people,
                                     make_rec)

P1, P2 = "+972501234567", "+972509999999"


def rec(table, key, name="", phones=(), emails=()):
    return make_rec(table, key, name, phones, emails)


def by_link(people):
    return {l: p for p in people for l in p.links}


def test_same_phone_in_any_format_is_one_person():
    recs = [rec(SUBMISSIONS, "s1", "Dana", ["050-123-4567"], ["dana@example.test"]),
            rec(BOOKINGS, "b1", "Dana L", [P1], ["other@example.test"]),
            rec(ORDERS, "o1", "Dana Levi", ["972501234567"], [])]
    people, review = compute_people(recs)
    assert len(people) == 1 and review == []
    assert people[0].phones == [P1]
    assert people[0].emails == ["dana@example.test", "other@example.test"]  # rule c: all emails kept


def test_same_email_with_no_phone_on_one_side_is_one_person():
    recs = [rec(SUBMISSIONS, "s1", "Dana", [P1], ["Dana@Example.test "]),
            rec(INVITES, "i1", "Dana", [], ["dana@example.test"])]
    people, _ = compute_people(recs)
    assert len(people) == 1 and len(people[0].links) == 2


def test_same_email_with_different_phones_is_not_merged_and_is_listed():
    recs = [rec(SUBMISSIONS, "s1", "A", [P1], ["same@example.test"]),
            rec(BOOKINGS, "b1", "B", [P2], ["same@example.test"])]
    people, review = compute_people(recs)
    assert len(people) == 2
    assert len(review) == 1 and review[0].kind == "email_multiple_phones" and review[0].value == "same@example.test"
    assert sorted(review[0].person_ids) == sorted(p.person_id for p in people)


def test_phoneless_record_joins_the_single_person_with_that_email_but_not_when_two_match():
    one = [rec(SUBMISSIONS, "s1", "A", [P1], ["x@example.test"]), rec(INVITES, "i1", "A", [], ["x@example.test"])]
    assert len(compute_people(one)[0]) == 1
    two = one + [rec(BOOKINGS, "b1", "B", [P2], ["x@example.test"])]
    people, review = compute_people(two)
    assert len(people) == 3 and len(review) == 1  # the phoneless record is not guessed into either person


def test_name_alone_never_merges():
    people, _ = compute_people([rec(SUBMISSIONS, "s1", "Dana Levi", [P1], []),
                                rec(BOOKINGS, "b1", "Dana Levi", [P2], [])])
    assert len(people) == 2


def test_records_without_phone_or_email_are_skipped():
    assert rec(SUBMISSIONS, "s1", "Nobody", ["abc"], ["not-an-email"]) is None
    assert rec(SUBMISSIONS, "s1", "Nobody", ["12"], [""]) is None


def test_the_known_test_account_pattern_is_one_person_with_all_records():
    """Two accounts and three orders on one phone, one account with no email: all one person."""
    recs = [rec(USERS, "u1", "Adi", ["0501234567"], []),
            rec(USERS, "u2", "Adi B", ["+972 50 123 4567"], ["adi@example.test"]),
            rec(ORDERS, "o1", "Adi", ["050-123-4567"], ["office@example.test"]),
            rec(ORDERS, "o2", "Adi", ["050-123-4567"], ["office@example.test"]),
            rec(ORDERS, "o3", "Adi", ["050-123-4567"], ["office@example.test"])]
    people, review = compute_people(recs)
    assert len(people) == 1 and len(people[0].links) == 5 and review == []
    assert people[0].display_name == "Adi"  # users come first in name priority, then by key


def test_ids_are_stable_across_runs_and_reuse_existing_ids():
    recs = [rec(SUBMISSIONS, "s1", "A", [P1], []), rec(BOOKINGS, "b1", "A", [P1], [])]
    first, _ = compute_people(recs)
    again, _ = compute_people(list(reversed(recs)))
    assert first[0].person_id == again[0].person_id
    kept, _ = compute_people(recs, {(SUBMISSIONS, "s1"): "11111111-1111-4111-8111-111111111111"})
    assert kept[0].person_id == "11111111-1111-4111-8111-111111111111"


def test_new_record_joining_two_existing_people_keeps_one_of_the_ids_not_both():
    a, b = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    recs = [rec(SUBMISSIONS, "s1", "A", [P1], ["a@example.test"]), rec(BOOKINGS, "b1", "A", [], ["b@example.test"]),
            rec(INVITES, "i1", "A", [], ["a@example.test", "b@example.test"])]
    people, _ = compute_people(recs, {(SUBMISSIONS, "s1"): b, (BOOKINGS, "b1"): a})
    assert len(people) == 1 and people[0].person_id == a


def test_same_input_gives_the_same_output():
    recs = [rec(SUBMISSIONS, "s%d" % i, "N%d" % i, [P1 if i % 2 else P2], ["e%d@example.test" % (i % 3)])
            for i in range(8)]
    one = compute_people(recs)
    two = compute_people(list(reversed(recs)))
    assert [(p.person_id, p.links) for p in one[0]] == [(p.person_id, p.links) for p in two[0]]
    assert [(r.value, r.person_ids) for r in one[1]] == [(r.value, r.person_ids) for r in two[1]]


class FakeCursor:
    def __init__(self, tables):
        self.tables, self.rows, self.sql = tables, [], []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        s = " ".join(sql.split())
        self.rows = []
        if s.startswith("SELECT source_table"):
            self.rows = self.tables.get("links", [])
        elif "FROM coaching_lead_submissions" in s:
            self.rows = self.tables.get("submissions", [])
        elif "FROM booking_notifications" in s:
            self.rows = self.tables.get("bookings", [])
        elif "FROM work_order_drafts" in s:
            self.rows = self.tables.get("orders", [])
        elif "FROM invites" in s:
            self.rows = self.tables.get("invites", [])
        elif "FROM user_profiles" in s:
            self.rows = self.tables.get("users", [])

    def fetchall(self):
        return self.rows


def run_sync(tables):
    cur = FakeCursor(tables)

    @contextmanager
    def ctx(commit=False):
        assert commit is True
        yield cur
    with patch.object(pp, "get_db_cursor", ctx):
        return pp.sync_people(), cur


TABLES = {
    "submissions": [{"submission_id": "s1", "name": "Dana", "email": "d@example.test", "contact_email": None,
                     "phone_e164": P1, "mobile_phone": None}],
    "bookings": [{"event_id": "e1", "payload": {"name": "Dana", "email": "d@example.test"}}],
    "orders": [{"order_id": "o1", "customer_name": "Dana", "customer_email": "x@example.test",
                "customer_phone": "050-123-4567"}],
    "invites": [], "users": [],
}


def test_sync_reads_all_sources_and_reports_counts():
    out, cur = run_sync(TABLES)
    assert out == {"people": 1, "review": 0, "records": 3}


def test_sync_writes_only_the_four_new_tables():
    _, cur = run_sync(TABLES)
    allowed = {"people", "person_identifiers", "person_links", "people_review"}
    for sql, _ in cur.sql:
        s = " ".join(sql.split())
        m = re.match(r"(INSERT INTO|DELETE FROM|UPDATE)\s+(\w+)", s)
        if m:
            assert m.group(2) in allowed, s
        assert not re.match(r"(DROP|ALTER|TRUNCATE|CREATE)", s, re.I)


def test_sync_takes_an_advisory_lock_and_is_idempotent():
    out1, cur1 = run_sync(TABLES)
    assert "pg_advisory_xact_lock" in cur1.sql[0][0]
    ids1 = [p[1][0] for p in cur1.sql if p[0].lstrip().startswith("INSERT INTO people(")]
    stored = [{"source_table": t, "source_key": k, "person_id": ids1[0]} for t, k in
              [(SUBMISSIONS, "s1"), (BOOKINGS, "e1"), (ORDERS, "o1")]]
    out2, cur2 = run_sync({**TABLES, "links": stored})
    ids2 = [p[1][0] for p in cur2.sql if p[0].lstrip().startswith("INSERT INTO people(")]
    assert out1 == out2 and ids1 == ids2


def test_loading_normalizes_old_phone_formats_and_skips_unplaceable_rows():
    tables = {"users": [{"user_id": "u1", "name": "A", "email": None, "phone_number": "050-123-4567"},
                        {"user_id": "u2", "name": "B", "email": None, "phone_number": "telegram-1"}],
              "submissions": [], "bookings": [], "orders": [], "invites": []}
    cur = FakeCursor(tables)
    recs = pp.load_records(cur)
    assert [(r.key, r.phones) for r in recs] == [("u1", (P1,))]


def test_sync_sql_only_reads_the_source_tables():
    _, cur = run_sync(TABLES)
    reads = [" ".join(s.split()) for s, _ in cur.sql if s.lstrip().upper().startswith("SELECT")]
    assert not any(re.search(r"\b(INSERT|UPDATE|DELETE)\b", r) for r in reads)


def test_migration_adds_only_four_new_tables():
    from pathlib import Path
    sql = Path(pp.__file__).parent.joinpath("migrations/20261004_people.sql").read_text()
    body = " ".join(l for l in sql.splitlines() if not l.strip().startswith("--")).upper()
    assert body.count("CREATE TABLE IF NOT EXISTS") == 4
    for name in ("PEOPLE (", "PERSON_IDENTIFIERS", "PERSON_LINKS", "PEOPLE_REVIEW"):
        assert name in body
    assert not any(w in body for w in ("DROP ", "DELETE FROM", "TRUNCATE", "ALTER ", "UPDATE ", "INSERT "))
    assert "PERSON_IDENTIFIERS_PHONE_UNIQUE ON PERSON_IDENTIFIERS (VALUE) WHERE KIND = 'PHONE'" in body
