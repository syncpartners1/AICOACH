"""The step 3 migration only creates three new tables and their indexes."""
import re
from pathlib import Path

from autogpt.coaching import people


def sql():
    p = Path(people.__file__).parent / "migrations" / "20261007_person_marks.sql"
    return " ".join(l for l in p.read_text().splitlines() if not l.strip().startswith("--"))


def test_only_creates_new_tables_and_indexes():
    body = sql()
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP)\b", body, re.I)
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", body)
    assert tables == ["person_marks", "person_notes", "join_invites_pending"]
    assert all(s.strip().startswith("CREATE") for s in body.split(";") if s.strip())


def test_no_foreign_key_so_marks_survive_the_people_rebuild():
    assert "REFERENCES" not in sql().upper()


def test_mark_kinds_states_and_one_open_invite():
    body = sql()
    assert "'intro', 'diagnostic', 'not_lead'" in body
    assert "'held', 'no_show', 'cleared', 'on', 'off'" in body
    assert "join_invites_one_open ON join_invites_pending (person_id) WHERE status IN ('pending', 'sending')" in body
