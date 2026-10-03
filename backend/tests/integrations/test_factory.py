import inspect
from datetime import datetime, timezone

import pytest

from app.integrations import factory
from app.integrations.excel.gateway import ExcelFormatError
from app.integrations.excel.source import ExcelIdpSource, resolve_path

from .samples import SAMPLES, TEMPLATES_DIR
from .synth import idp_row, ifs_row, make_idp, make_ifs


def test_factory_signatures_exact():
    sig = lambda f: str(inspect.signature(f))  # noqa: E731
    assert sig(factory.build_calendar) == "() -> 'JalaliCalendar'"
    assert sig(factory.build_excel_gateway) == "() -> 'ExcelGateway'"
    assert sig(factory.build_employee_source) == "(kind: \"Literal['excel', 'ifs']\", config: 'dict') -> 'EmployeeSource'"
    assert sig(factory.build_email_sender) == "(kind: \"Literal['smtp', 'graph']\", config: 'dict') -> 'EmailSender'"
    assert sig(factory.build_letter_renderer) == "(templates_dir: 'str') -> 'LetterRenderer'"


def test_contract_shapes():
    cal = factory.build_calendar()
    for m in ("to_jalali", "to_gregorian", "format", "add_days", "number_to_words_fa", "to_persian_digits",
              "to_latin_digits"):
        assert callable(getattr(cal, m))
    gw = factory.build_excel_gateway()
    for m in ("read_idp", "read_employees", "read_legacy", "write_legacy"):
        assert callable(getattr(gw, m))
    r = factory.build_letter_renderer(TEMPLATES_DIR)
    assert r.render("level3_request", SAMPLES["level3_request"], "fa").kind == "level3_request"
    assert list(r.required_fields("level3_request"))


def test_employee_source_excel(tmp_path):
    p = make_ifs(tmp_path / "ifs.xlsx", [ifs_row(1), ifs_row(2)])
    src = factory.build_employee_source("excel", {"path": str(p)})
    ok, msg = src.test_connection()
    assert ok and "2 employee" in msg
    assert len(list(src.fetch_employees())) == 2
    future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert list(src.fetch_employees(future)) == []
    assert len(list(src.fetch_employees(datetime(2000, 1, 1)))) == 2
    # watch_dir picks the newest workbook and ignores lock files
    (tmp_path / "~$ifs.xlsx").write_bytes(b"x")
    src2 = factory.build_employee_source("excel", {"watch_dir": str(tmp_path)})
    assert len(list(src2.fetch_employees())) == 2
    idp = make_idp(tmp_path / "idp.xlsx", [idp_row(1)])
    assert len(list(ExcelIdpSource({"path": str(idp)}).fetch_idp())) == 1


def test_excel_source_failures(tmp_path):
    ok, msg = factory.build_employee_source("excel", {"path": str(tmp_path / "missing.xlsx")}).test_connection()
    assert not ok and "missing.xlsx" in msg
    with pytest.raises(ExcelFormatError):
        resolve_path({})
    with pytest.raises(FileNotFoundError):
        resolve_path({"watch_dir": str(tmp_path)})


def test_ifs_smtp_graph_kinds():
    ifs = factory.build_employee_source("ifs", {"base_url": "https://ifs.example.test", "auth_mode": "basic",
                                                "username": "u", "password": "p"})
    assert hasattr(ifs, "fetch_employees") and hasattr(ifs, "test_connection")
    assert factory.build_email_sender("smtp", {"host": "h", "from_addr": "a@example.test"}).test_connection
    assert factory.build_email_sender("graph", {"tenant_id": "t", "client_id": "c", "client_secret": "s",
                                                "sender": "a@example.test"}).send
    with pytest.raises(ValueError):
        factory.build_employee_source("ldap", {})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        factory.build_email_sender("pigeon", {})  # type: ignore[arg-type]
