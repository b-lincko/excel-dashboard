from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import AppConfig  # noqa: E402
from app.domain import (  # noqa: E402
    apply_site_on_record,
    filter_site_items,
    infer_camp_site,
    is_delayed,
    is_overdue,
    matches_filters,
    site_choices,
)


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
        assert is_delayed({**past, "status": status}, cfg) is False
        if status.upper() != "PLACED":
            assert is_overdue({**past, "status": status}, cfg) is False
            assert matches_filters({**past, "status": status}, {"flag": "overdue"}, cfg) is False
    # PLACED with a past due date is not overdue — overdue for PLACED is ETA (closed_date).
    assert is_overdue({**past, "status": "PLACED"}, cfg) is False
    assert is_overdue({"status": "PLACED", "closed_date": "2000-01-01"}, cfg) is True
    assert is_overdue({"status": "PLACED", "closed_date": "2099-12-31"}, cfg) is False
    assert matches_filters({"status": "PLACED", "closed_date": "2000-01-01"}, {"flag": "overdue"}, cfg) is True


def test_camp_sites_are_filter_chips_not_worksheet_names():
    cfg = AppConfig()
    names = [n.lower() for n in site_choices(cfg)]
    assert "site - 1" not in names
    assert "l1" not in names
    items = filter_site_items(cfg)
    ids = [i["id"] for i in items]
    labels = [i["label"] for i in items]
    assert "SH5-S1" in ids
    assert "Site - 1" in labels
    assert "Site - 4A" in labels
    assert "SH1-LS2" in ids
    assert "LS2" in labels
    assert "L7" in labels
    assert "SH5" in ids
    assert "SH1" in ids
    assert "Office" in ids
    assert "SH5-SH1" in ids


def test_infer_camp_site_from_asset_name():
    cfg = AppConfig()
    assert infer_camp_site({"department": "SH5-SH1", "location": "S1-B406-RXXX-CRAC 01"}, cfg)["id"] == "SH5-S1"
    assert infer_camp_site({"department": "SH5-SH1", "location": "S4A-B503-CIVIL GEN"}, cfg)["id"] == "SH5-S4A"
    assert infer_camp_site({"department": "SH5-SH1", "location": "LS1-BCLC-RCOR-FIP 03"}, cfg)["id"] == "SH1-LS1"
    assert infer_camp_site({"department": "SH5-SH1", "location": "L1-BCT-RTOP-CHWP P03"}, cfg)["id"] == "SH1-L1"
    assert infer_camp_site({"department": "SH5-SH1", "location": "SITE - 7 PUMP"}, cfg)["id"] == "SH5-S7"
    assert infer_camp_site({"department": "F5", "location": "S1-B406-x"}, cfg) is None


def test_filter_matches_camp_and_group_not_sheet_rewrite():
    cfg = AppConfig()
    rec = {"department": "SH5-SH1", "location": "S7-B805-x", "status": "OPEN"}
    assert matches_filters(rec, {"department": ["SH5-S7"]}, cfg) is True
    assert matches_filters(rec, {"department": ["Site - 7"]}, cfg) is True
    assert matches_filters(rec, {"department": ["SH5"]}, cfg) is True
    assert matches_filters(rec, {"department": ["SH5-SH1"]}, cfg) is True
    assert matches_filters(rec, {"department": ["SH1"]}, cfg) is False
    assert matches_filters(rec, {"department": ["F5"]}, cfg) is False
    sh1 = {"department": "SH5-SH1", "location": "L3-BGEN-RGEN-GEN", "status": "OPEN"}
    assert matches_filters(sh1, {"department": ["SH1"]}, cfg) is True
    assert matches_filters(sh1, {"department": ["L3"]}, cfg) is True
    assert matches_filters(sh1, {"department": ["SH5"]}, cfg) is False


def test_apply_site_keeps_excel_sheet_label():
    out = apply_site_on_record({"department": "Site - 1"}, AppConfig())
    assert out["department"] == "SH5-SH1"
    assert out["camp_site"] == "SH5-S1"
    out2 = apply_site_on_record({"department": "SH5-SH1", "camp_site": "LS2"}, AppConfig())
    assert out2["department"] == "SH5-SH1"
    assert out2["camp_site"] == "SH1-LS2"


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
    assert resolve_data_sheet("Site - 1", available, labels) == "Linkco_MR_Log (SH5 & SH1)"
    assert resolve_data_sheet("SH5-S7", available, labels) == "Linkco_MR_Log (SH5 & SH1)"
    assert resolve_data_sheet("LS1", available, labels) == "Linkco_MR_Log (SH5 & SH1)"
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


def test_mindmap_sites_include_camps():
    from app.stats import mindmap

    recs = [
        {"department": "SH5-SH1", "location": "S3-B201-x", "status": "OPEN"},
        {"department": "SH5-SH1", "location": "L1-BCT-x", "status": "CLOSED"},
        {"department": "F5", "location": "F5-x", "status": "OPEN"},
    ]
    mm = mindmap(recs)
    sites = next(b for b in mm["branches"] if b["id"] == "sites")
    labels = [c["label"] for c in sites["children"]]
    ids = [c["filter"]["department"] for c in sites["children"]]
    assert "Site - 3" in labels
    assert "L1" in labels
    assert "F5" in labels
    assert "SH5" in labels
    assert "SH1" in labels
    assert "SH5-S3" in ids
    sh5 = next(c for c in sites["children"] if c["label"] == "SH5")
    assert any(ch["label"] == "Site - 3" for ch in (sh5.get("children") or []))


def test_search_q_matches_camp_site_label():
    cfg = AppConfig()
    rec = {"department": "SH5-SH1", "location": "S3-B201-x", "status": "OPEN", "work_order_id": "481000"}
    assert matches_filters(rec, {"q": "Site - 3"}, cfg) is True
    assert matches_filters(rec, {"q": "SH5-S3"}, cfg) is True
    assert matches_filters(rec, {"q": "LS2"}, cfg) is False


def test_suggest_includes_camp_sites():
    from app import database

    groups = database.suggest_workspace("Site - 3", limit=8)
    ids = [s.get("id") for s in (groups.get("sites") or [])]
    labels = [s.get("label") for s in (groups.get("sites") or [])]
    assert "SH5-S3" in ids
    assert "Site - 3" in labels


def test_replace_excel_file_falls_back_when_busy(tmp_path, monkeypatch):
    import errno

    from app.excel.service import _replace_excel_file

    src = tmp_path / "new.xlsx"
    dest = tmp_path / "file.xlsx"
    src.write_bytes(b"hello-new-bytes")
    dest.write_bytes(b"old")

    def boom(_a, _b):
        raise OSError(errno.EBUSY, "Device or resource busy")

    monkeypatch.setattr("app.excel.service.os.replace", boom)
    _replace_excel_file(src, dest)
    assert dest.read_bytes() == b"hello-new-bytes"
    assert not src.exists()


def test_message_notifications_for_chat():
    from app import database, notify

    database.init_db()
    thread = database.get_or_create_dm("admin", "manager")
    sent = notify.notify_thread_message("admin", thread, "Please check the RFQ")
    assert "manager" in sent
    assert "admin" not in sent
    items = database.list_notifications("manager")
    assert any(n.get("kind") == "message" and "Please check the RFQ" in (n.get("body") or "") for n in items)
