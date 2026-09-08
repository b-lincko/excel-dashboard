from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain import (  # noqa: E402
    canonical_priority,
    is_blockade,
    is_placed,
    is_status_open,
    matches_filters,
)
from app.stats import blockades, group_by, kpis  # noqa: E402


def test_canonical_priority_collapses_case():
    assert canonical_priority("LOW") == "Low"
    assert canonical_priority("low") == "Low"
    assert canonical_priority("Low") == "Low"
    assert canonical_priority("MEDIUM") == "Medium"
    assert canonical_priority("Medium") == "Medium"
    assert canonical_priority("HIGH") == "High"
    assert canonical_priority("") == ""


def test_priority_group_by_merges_case():
    recs = [
        {"priority": "LOW", "status": "OPEN"},
        {"priority": "Low", "status": "OPEN"},
        {"priority": "MEDIUM", "status": "CLOSED"},
        {"priority": "Medium", "status": "OPEN"},
        {"priority": "HIGH", "status": "PLACED"},
    ]
    rows = group_by(recs, "priority")
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"Low", "Medium", "High"}
    assert by_name["Low"]["total"] == 2
    assert by_name["Medium"]["total"] == 2
    assert by_name["High"]["total"] == 1


def test_blockades_exclude_open_and_placed():
    recs = [
        {"status": "OPEN"},
        {"status": "Open"},
        {"status": "PLACED"},
        {"status": "UNDER NTP"},
        {"status": "ON HOLD"},
        {"status": "UNDER GATEPASS"},
        {"status": "CLOSED"},
        {"status": "PENDING"},
    ]
    assert is_status_open({"status": "OPEN"})
    assert is_status_open({"status": "Open"})
    assert is_status_open({"status": "OPEN."})
    assert is_placed({"status": "PLACED"})
    assert not is_blockade({"status": "OPEN"})
    assert not is_blockade({"status": "PLACED"})
    assert not is_blockade({"status": "CLOSED"})
    assert is_blockade({"status": "UNDER NTP"})
    assert is_blockade({"status": "ON HOLD"})
    assert is_blockade({"status": "UNDER GATEPASS"})
    assert is_blockade({"status": "PENDING"})

    k = kpis(recs)
    assert k["open"] == 2
    assert k["placed"] == 1
    assert k["blockades"] == 4
    names = {row["name"] for row in blockades(recs)}
    assert "OPEN" not in names
    assert "Open" not in names
    assert "PLACED" not in names
    assert "CLOSED" not in names
    assert "UNDER NTP" in names
    assert "ON HOLD" in names


def test_blockade_and_open_flags():
    recs = [
        {"status": "OPEN", "priority": "LOW"},
        {"status": "UNDER NTP", "priority": "low"},
        {"status": "PLACED", "priority": "Medium"},
    ]
    assert matches_filters(recs[0], {"flag": "open"})
    assert not matches_filters(recs[0], {"flag": "blockade"})
    assert matches_filters(recs[1], {"flag": "blockade"})
    assert not matches_filters(recs[1], {"flag": "open"})
    assert not matches_filters(recs[2], {"flag": "blockade"})
    assert matches_filters(recs[0], {"priority": ["Low"]})
    assert matches_filters(recs[1], {"priority": ["Low"]})
