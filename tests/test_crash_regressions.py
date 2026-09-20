"""Regression tests for runtime crashes found in the bot and auth paths."""
import ast
from pathlib import Path

from autogpt.coaching import storage


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table, operation, payload=None):
        self.table = table
        self.operation = operation
        self.payload = payload
        self.field = None
        self.value = None

    def select(self, *_args):
        self.operation = "select"
        return self

    def eq(self, field, value):
        self.field, self.value = field, value
        return self

    def update(self, payload):
        self.operation, self.payload = "update", payload
        return self

    def insert(self, payload):
        self.operation, self.payload = "insert", payload
        return self

    def execute(self):
        if self.operation == "select":
            return _Result([
                row.copy() for row in self.table.rows
                if row.get(self.field) == self.value
            ])
        if self.operation == "update":
            for row in self.table.rows:
                if row.get(self.field) == self.value:
                    row.update(self.payload)
            return _Result([])
        if self.operation == "insert":
            self.table.rows.append(self.payload.copy())
            return _Result([self.payload.copy()])
        raise AssertionError(self.operation)


class _Table:
    def __init__(self):
        self.rows = []

    def select(self, *_args):
        return _Query(self, "select")

    def update(self, payload):
        return _Query(self, "update", payload)

    def insert(self, payload):
        return _Query(self, "insert", payload)


class _DB:
    def __init__(self):
        self.user_profiles = _Table()

    def table(self, name):
        assert name == "user_profiles"
        return self.user_profiles


def test_google_auth_creates_new_profile(monkeypatch):
    db = _DB()
    monkeypatch.setattr(storage, "_get_client", lambda: db)
    profile = storage.google_auth("gid-1", "Ada", "ada@example.com", "+15551234567")
    assert profile.user_id
    assert profile.email == "ada@example.com"
    assert profile.phone_number == "+15551234567"
    assert db.user_profiles.rows[0]["google_id"] == "gid-1"


def test_funnel_handlers_define_lang_before_use():
    tree = ast.parse(Path("autogpt/coaching/telegram_bot.py").read_text())
    names = {"funnel_start_cb", "funnel_receive_q1", "funnel_receive_q2", "funnel_receive_q3"}
    funcs = {node.name: node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)}
    for name in names:
        first = funcs[name].body[1]  # body[0] is the docstring
        assert isinstance(first, ast.Assign)
        assert isinstance(first.targets[0], ast.Name)
        assert first.targets[0].id == "lang"


def test_whatsapp_summary_has_translation_catalog():
    import autogpt.coaching.whatsapp_bot as whatsapp_bot
    assert "wa_summary_title" in whatsapp_bot.S_EN
