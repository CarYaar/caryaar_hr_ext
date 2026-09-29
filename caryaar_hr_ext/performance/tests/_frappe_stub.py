"""A small in-memory stand-in for Frappe, for unit tests of meter.py, review_pack.py,
setup.py and the Goal Meter Reading controller without a bench.

It is not Frappe. Only the calls those modules make are implemented, and anything
else raises, so a test fails loudly instead of passing on a silent no-op. Documents
are plain dicts keyed by doctype and name; filters support the operators the
performance modules use (=, !=, in, not in, <, <=, >, >=, between, like, is set)."""
from __future__ import annotations

import importlib
import sys
import traceback
import types
from datetime import date, datetime, time


class _Dict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


class ValidationError(Exception):
    pass


class PermissionError(Exception):  # noqa: A001 - mirrors frappe.PermissionError
    pass


class DoesNotExistError(Exception):
    pass


def getdate(value=None):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def get_datetime(value=None):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value).replace("T", " ")[:19])


def _temporal(value):
    if isinstance(value, (date, datetime)):
        return get_datetime(value)
    if isinstance(value, str) and len(value) >= 10 and value[4] == "-" and value[7] == "-":
        try:
            return get_datetime(value)
        except ValueError:
            return value
    return value


def _match(doc: dict, key: str, cond) -> bool:
    val = doc.get(key)
    if not isinstance(cond, (list, tuple)):
        return val == cond
    op, arg = cond[0], cond[1]
    if op == "=":
        return val == arg
    if op == "!=":
        return val != arg
    if op == "in":
        return val in arg
    if op == "not in":
        return val not in arg
    if op == "is":
        return (val not in (None, "")) if arg == "set" else (val in (None, ""))
    if op == "like":
        return str(arg).strip("%") in str(val or "")
    if val in (None, ""):
        return False
    v = _temporal(val)
    if op == "between":
        return _temporal(arg[0]) <= v <= _temporal(arg[1])
    a = _temporal(arg)
    return {"<": v < a, "<=": v <= a, ">": v > a, ">=": v >= a}[op]


class FakeDB:
    def __init__(self):
        self.store: dict[str, dict[str, dict]] = {}
        self.singles: dict[tuple[str, str], object] = {}
        self.sql_handler = None

    # ─── reads ────────────────────────────────────────────────────────────
    def _rows(self, doctype, filters=None) -> list[dict]:
        rows = list(self.store.get(doctype, {}).values())
        if isinstance(filters, dict):
            return [r for r in rows if all(_match(r, k, c) for k, c in filters.items())]
        if isinstance(filters, (list, tuple)):
            return [r for r in rows if all(_match(r, f, (op, v)) for f, op, v in filters)]
        return rows

    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None, limit=None,
                limit_page_length=None, **_):
        rows = self._rows(doctype, filters)
        if order_by:
            field, _, direction = order_by.partition(" ")
            rows.sort(key=lambda r: (r.get(field) is None, str(r.get(field))), reverse=direction.strip().lower() == "desc")
        limit = limit or limit_page_length
        if limit:
            rows = rows[:limit]
        if pluck:
            return [r.get(pluck) for r in rows]
        if fields:
            return [_Dict({f: r.get(f) for f in fields}) for r in rows]
        return [_Dict(r) for r in rows]

    get_list = get_all

    def get_value(self, doctype, name=None, fieldname=None, as_dict=False, **_):
        if isinstance(name, dict):
            rows = self._rows(doctype, name)
            doc = rows[0] if rows else None
        else:
            doc = self.store.get(doctype, {}).get(name)
        if doc is None:
            return None
        if isinstance(fieldname, (list, tuple)):
            picked = {f: doc.get(f) for f in fieldname}
            return _Dict(picked) if as_dict else tuple(picked.values())
        return doc.get(fieldname or "name")

    def exists(self, doctype, name=None, **_):
        if isinstance(name, dict):
            return bool(self._rows(doctype, name))
        return name in self.store.get(doctype, {})

    def count(self, doctype, filters=None, **_):
        return len(self._rows(doctype, filters))

    def get_single_value(self, doctype, field):
        return self.singles.get((doctype, field))

    def sql(self, query, values=None, as_dict=False, **_):
        if self.sql_handler is None:
            raise NotImplementedError("frappe.db.sql needs FakeDB.sql_handler in this test")
        return self.sql_handler(query, values)

    # ─── writes ───────────────────────────────────────────────────────────
    def set_value(self, doctype, name, field, value=None, update_modified=True, **_):
        doc = self.store[doctype][name]
        if isinstance(field, dict):
            doc.update(field)
        else:
            doc[field] = value

    def set_single_value(self, doctype, field, value):
        self.singles[(doctype, field)] = value

    def delete(self, doctype, filters=None):
        for r in self._rows(doctype, filters):
            del self.store[doctype][r["name"]]

    @staticmethod
    def escape(value, percent=True):
        return "'" + str(value).replace("'", "''") + "'"

    def savepoint(self, name):
        pass

    def rollback(self, save_point=None):
        pass

    def commit(self):
        pass


class Document(_Dict):
    """Base for FakeDoc and for the real controllers imported under the stub."""

    def __init__(self, fake, doctype, data):
        super().__init__(data)
        dict.__setitem__(self, "doctype", doctype)
        object.__setattr__(self, "_fake", fake)

    def _name(self):
        if self.get("name"):
            return self["name"]
        if hasattr(self, "autoname"):
            self.autoname()
            if self.get("name"):
                return self["name"]
        rule = self._fake.autonames.get(self.doctype)
        if rule:
            return str(self[rule])
        n = self._fake.counter = self._fake.counter + 1
        return f"{self.doctype.upper().replace(' ', '-')}-{n:04d}"

    def insert(self, ignore_permissions=False, **_):
        self["name"] = self._name()
        self._fake.fetch_from(self)
        if hasattr(self, "validate"):
            self.validate()
        self._fake.db.store.setdefault(self.doctype, {})[self["name"]] = dict(self)
        if hasattr(self, "after_insert"):
            self.after_insert()
        if hasattr(self, "on_update"):
            self.on_update()
        return self

    def save(self, ignore_permissions=False, **_):
        self._fake.fetch_from(self)
        if hasattr(self, "validate"):
            self.validate()
        self._fake.db.store[self.doctype][self["name"]] = dict(self)
        if hasattr(self, "on_update"):
            self.on_update()
        return self

    def reload(self):
        self.update(self._fake.db.store[self.doctype][self["name"]])

    # what real controllers call on a Document
    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):
        self[key] = value

    def append(self, table, row=None):
        rows = self.get(table) or []
        rows.append(dict(row or {}))
        self[table] = rows
        return rows[-1]

    def is_new(self):
        return not self.get("name") or self.get("name") not in self._fake.db.store.get(self.doctype, {})

    def add_comment(self, comment_type="Comment", text=""):
        self._fake.comments.append((self.doctype, self.get("name"), comment_type, text))

    def db_set(self, field, value=None, **_):
        self._fake.db.set_value(self.doctype, self["name"], field, value)
        if isinstance(field, dict):
            self.update(field)
        else:
            self[field] = value


class FakeFrappe:
    """Everything reachable as ``frappe.*`` from the modules under test."""

    def __init__(self, today: date, roles=("HR Manager",), user="hr@caryaar.test"):
        self.db = FakeDB()
        self.today = today
        self.roles = set(roles)
        self.session = _Dict(user=user)
        self.errors: list[tuple[str, str]] = []
        self.mails: list[dict] = []
        self.rendered: list[tuple[str, dict]] = []
        self.counter = 0
        self.controllers: dict[str, type] = {}
        self.autonames = {"Goal Meter": "goal", "Plane Work Item": "issue_id", "Employee": "name"}
        self.fetch_rules = {("Goal Meter", "employee"): ("goal", "Goal", "employee"),
                            ("Goal Meter Reading", "employee"): ("goal", "Goal", "employee")}
        self.permission_denied: set[tuple[str, str]] = set()
        self.comments: list[tuple] = []
        self.messages: list[str] = []
        self._dict = _Dict
        self.ValidationError = ValidationError
        self.PermissionError = PermissionError
        self.DoesNotExistError = DoesNotExistError

    # documents
    def fetch_from(self, doc):
        for (dt, field), (link, link_dt, src) in self.fetch_rules.items():
            if doc.doctype == dt and doc.get(link):
                doc[field] = self.db.get_value(link_dt, doc[link], src)

    def get_doc(self, arg, name=None, **_):
        if isinstance(arg, dict):
            doctype = arg["doctype"]
            cls = self.controllers.get(doctype, Document)
            return cls(self, doctype, {k: v for k, v in arg.items() if k != "doctype"})
        data = self.db.store.get(arg, {}).get(name)
        if data is None:
            raise DoesNotExistError(f"{arg} {name} not found")
        cls = self.controllers.get(arg, Document)
        return cls(self, arg, dict(data))

    def new_doc(self, doctype):
        return self.get_doc({"doctype": doctype})

    def get_all(self, *a, **kw):
        return self.db.get_all(*a, **kw)

    get_list = get_all

    def delete_doc(self, doctype, name, **_):
        self.db.store.get(doctype, {}).pop(name, None)

    # control flow
    def throw(self, msg, exc=None, **_):
        raise (exc or ValidationError)(msg)

    def msgprint(self, msg, **_):
        self.messages.append(str(msg))

    def only_for(self, roles, **_):
        wanted = {roles} if isinstance(roles, str) else set(roles)
        if not wanted & self.roles:
            raise PermissionError(f"needs one of {sorted(wanted)}")

    def has_permission(self, doctype, ptype="read", doc=None, throw=False, **_):
        name = doc if isinstance(doc, str) else (doc or {}).get("name")
        ok = (doctype, name) not in self.permission_denied and (doctype, "*") not in self.permission_denied
        if not ok and throw:
            raise PermissionError(f"no {ptype} on {doctype} {name}")
        return ok

    def get_roles(self, user=None):
        return sorted(self.roles)

    def log_error(self, title="", message="", **_):
        self.errors.append((title, message))

    def get_traceback(self):
        return traceback.format_exc()

    def sendmail(self, **kw):
        self.mails.append(kw)

    def render_template(self, path, context=None, **_):
        self.rendered.append((path, context or {}))
        return f"<rendered {path}>"

    def whitelist(self, *a, **kw):
        def deco(fn):
            return fn
        return deco

    def logger(self, *a, **kw):
        return types.SimpleNamespace(info=lambda *x, **y: None, warning=lambda *x, **y: None,
                                     error=lambda *x, **y: None)

    # frappe.utils
    def utils_module(self):
        fake = self
        u = types.ModuleType("frappe.utils")
        u.getdate = getdate
        u.get_datetime = get_datetime
        u.flt = lambda v, precision=None: float(v or 0)
        u.cint = lambda v: int(v or 0)
        u.nowdate = lambda: fake.today.isoformat()
        u.now = lambda: datetime.combine(fake.today, time(23, 45)).isoformat(sep=" ")
        u.now_datetime = lambda: datetime.combine(fake.today, time(23, 45))
        u.formatdate = lambda v, fmt=None: getdate(v).strftime("%d-%b-%Y") if getdate(v) else ""
        u.add_days = lambda d, n: getdate(d) + __import__("datetime").timedelta(days=n)
        return u


TARGET_MODULES = (
    "caryaar_hr_ext.caryaar_hr_ext.doctype.goal_meter.goal_meter",
    "caryaar_hr_ext.caryaar_hr_ext.doctype.goal_one_on_one.goal_one_on_one","caryaar_hr_ext.performance.meter", "caryaar_hr_ext.performance.review_pack",
                  "caryaar_hr_ext.performance.setup", "caryaar_hr_ext.performance.api",
                  "caryaar_hr_ext.caryaar_hr_ext.doctype.goal_meter_reading.goal_meter_reading")


def install(monkeypatch, today: date, roles=("HR Manager",), user="hr@caryaar.test") -> FakeFrappe:
    """Put the stub in sys.modules and (re)load the modules under test against it.
    Returns the FakeFrappe so the test can seed documents and read what was written."""
    fake = FakeFrappe(today, roles, user)
    frappe = types.ModuleType("frappe")
    for attr in ("db", "session", "get_doc", "new_doc", "get_all", "get_list", "delete_doc", "throw", "msgprint", "only_for",
                 "has_permission", "get_roles", "log_error", "get_traceback", "sendmail", "render_template",
                 "whitelist", "logger", "_dict", "ValidationError", "PermissionError", "DoesNotExistError"):
        setattr(frappe, attr, getattr(fake, attr))
    frappe.utils = fake.utils_module()
    model = types.ModuleType("frappe.model")
    document = types.ModuleType("frappe.model.document")
    document.Document = Document
    model.document = document
    frappe.model = model
    monkeypatch.setitem(sys.modules, "frappe", frappe)
    monkeypatch.setitem(sys.modules, "frappe.utils", frappe.utils)
    monkeypatch.setitem(sys.modules, "frappe.model", model)
    monkeypatch.setitem(sys.modules, "frappe.model.document", document)
    for mod in TARGET_MODULES:
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
        else:
            importlib.import_module(mod)
    ctrl = sys.modules[TARGET_MODULES[-1]]
    fake.controllers["Goal Meter Reading"] = ctrl.GoalMeterReading
    fake.controllers["Goal Meter"] = sys.modules["caryaar_hr_ext.caryaar_hr_ext.doctype.goal_meter.goal_meter"].GoalMeter
    fake.controllers["Goal One on One"] = sys.modules["caryaar_hr_ext.caryaar_hr_ext.doctype.goal_one_on_one.goal_one_on_one"].GoalOneonOne
    return fake


def seed(fake: FakeFrappe, doctype: str, **fields) -> dict:
    """Store a document directly (no hooks), returning it. ``name`` defaults to the doctype's autoname field."""
    doc = dict(fields)
    if "name" not in doc:
        rule = fake.autonames.get(doctype)
        if rule and doc.get(rule):
            doc["name"] = str(doc[rule])
        else:
            fake.counter += 1
            doc["name"] = f"{doctype.upper().replace(' ', '-')}-{fake.counter:04d}"
    fake.db.store.setdefault(doctype, {})[doc["name"]] = doc
    return doc
