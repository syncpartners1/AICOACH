"""The CHECK widening for the interest source is the only change in the migration."""
import re
from pathlib import Path

from autogpt.coaching import people


def sql():
    p = Path(people.__file__).parent / "migrations" / "20261006_person_links_interest.sql"
    return " ".join(l for l in p.read_text().splitlines() if not l.strip().startswith("--"))


def test_migration_only_widens_the_person_links_check():
    body = sql()
    statements = [s.strip() for s in body.split(";") if s.strip()]
    assert len(statements) == 2
    assert statements[0] == "ALTER TABLE person_links DROP CONSTRAINT IF EXISTS person_links_source_table_check"
    assert statements[1].startswith("ALTER TABLE person_links ADD CONSTRAINT person_links_source_table_check CHECK")
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|CREATE|DROP TABLE)\b", body, re.I)


def test_new_check_allows_exactly_the_sources_the_code_links():
    allowed = set(re.findall(r"'([a-z_]+)'", sql().split("CHECK", 1)[1]))
    assert allowed == {people.SUBMISSIONS, people.BOOKINGS, people.ORDERS, people.INVITES, people.USERS,
                       people.INTEREST}


def test_the_first_people_migration_has_the_constraint_name_this_one_drops():
    first = (Path(people.__file__).parent / "migrations" / "20261004_people.sql").read_text()
    # an unnamed inline CHECK on column source_table of person_links is named person_links_source_table_check by Postgres
    assert "source_table TEXT NOT NULL CHECK (source_table IN" in first
