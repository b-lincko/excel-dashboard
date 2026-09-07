from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import AppConfig  # noqa: E402
from app.domain import is_delayed, is_overdue, matches_filters, site_choices  # noqa: E402


def test_site_choices_include_office_and_accommodations():
    names = site_choices(AppConfig())
    lower = [n.lower() for n in names]
    assert "office" in lower
    assert "accommodations" in lower
    assert "sh5-sh1" in lower
    assert "f5" in lower
    assert "all sites" not in lower


def test_delay_only_open_past_due_and_pending():
    cfg = AppConfig()
    assert is_overdue({"status": "OPEN", "due_date": "2000-01-01"}, cfg) is True
    assert is_delayed({"status": "OPEN", "due_date": "2000-01-01"}, cfg) is True
    assert is_overdue({"status": "OPEN", "due_date": "2099-12-31"}, cfg) is False
    assert is_overdue({"status": "OPEN", "due_date": ""}, cfg) is False
    assert is_overdue({"status": "PENDING", "due_date": "2099-12-31"}, cfg) is True
    assert is_overdue({"status": "Pending", "due_date": ""}, cfg) is True
    assert is_overdue({"status": "UNDER NTP", "due_date": "2000-01-01"}, cfg) is False
    assert is_overdue({"status": "ON HOLD", "due_date": "2000-01-01"}, cfg) is False


def test_delay_excludes_close_placed_estimation_inspection():
    cfg = AppConfig()
    past = {"due_date": "2000-01-01"}
    for status in (
        "CLOSED",
        "Close",
        "PLACED",
        "ESTIMATION PRICE",
        "Delivered Material Inspection",
    ):
        assert is_overdue({**past, "status": status}, cfg) is False
        assert is_delayed({**past, "status": status}, cfg) is False
        assert matches_filters({**past, "status": status}, {"flag": "overdue"}, cfg) is False


def test_resolve_data_sheet_rejects_missing_office_tab():
    from app.excel.service import resolve_data_sheet

    labels = {
        "Linkco_MR_Log (SH5 & SH1)": "SH5-SH1",
        "Linkco_MR_Log (F5)": "F5",
        "Linkco_MR_Log (Office)": "Office",
        "Linkco_MR_Log (Accommodations)": "Accommodations",
    }
    available = ["Linkco_MR_Log (SH5 & SH1)", "Linkco_MR_Log (F5)"]
    assert resolve_data_sheet("SH5-SH1", available, labels) == "Linkco_MR_Log (SH5 & SH1)"
    assert resolve_data_sheet("F5", available, labels) == "Linkco_MR_Log (F5)"
    assert resolve_data_sheet("", available, labels) == available[0]
    try:
        resolve_data_sheet("Office", available, labels)
        raise AssertionError("Office without a sheet should fail")
    except ValueError as exc:
        assert "Office" in str(exc)
    try:
        resolve_data_sheet("Accommodations", available, labels)
        raise AssertionError("Accommodations without a sheet should fail")
    except ValueError as exc:
        assert "Accommodations" in str(exc)


def test_message_notifications_for_chat():
    from app import database, notify

    database.init_db()
    thread = database.get_or_create_dm("admin", "manager")
    sent = notify.notify_thread_message("admin", thread, "Please check the RFQ")
    assert "manager" in sent
    assert "admin" not in sent
    items = database.list_notifications("manager")
    assert any(n.get("kind") == "message" and "Please check the RFQ" in (n.get("body") or "") for n in items)
