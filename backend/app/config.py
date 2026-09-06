from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
BACKUP_DIR = ROOT / "backups"
DB_PATH = DATA_DIR / "woms.db"
CONFIG_PATH = DATA_DIR / "app_config.json"
DEFAULT_EXCEL = ROOT / "file.xlsx"


def norm_header(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split())


class ColumnMapping(BaseModel):
    work_order_id: str = "IM Work Order #"
    created_date: str = "MR Received Date"
    scheduled_date: str = "Date of PO / Expected PO / RFQ Sent"
    due_date: str = "Due date (Approx. 2 weeks)"
    completion_date: str = "IM WO Completion"
    closed_date: str = "ETA / Expected Date of RFQ Response"
    status: str = "STATUS"
    priority: str = "WO Priority Level"
    department: str = ""
    location: str = "WO Asset Name"
    assigned_to: str = "Assign to"
    work_type: str = "Purchase Type"
    description: str = "Required Material Details"
    issue: str = "Delivery Status"
    delay_reason: str = "Delivery Status"
    remarks: str = "REMARKS / NOTES"
    created_by: str = ""
    last_updated: str = ""
    supplier: str = "Supplier Name"
    po_number: str = "PO NO #"

    def excel_to_internal(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for field, col in self.model_dump().items():
            key = norm_header(col)
            if key:
                out[key] = field
        return out

    def internal_to_excel(self) -> dict[str, str]:
        return {k: norm_header(v) for k, v in self.model_dump().items() if norm_header(v)}


class AppConfig(BaseModel):
    excel_path: str = str(DEFAULT_EXCEL)
    worksheet_name: str = "Linkco_MR_Log (SH5 & SH1)"
    worksheets: list[str] = Field(
        default_factory=lambda: [
            "Linkco_MR_Log (SH5 & SH1)",
            "Linkco_MR_Log (F5)",
        ]
    )
    worksheet_labels: dict[str, str] = Field(
        default_factory=lambda: {
            "Linkco_MR_Log (SH5 & SH1)": "SH5-SH1",
            "Linkco_MR_Log (F5)": "F5",
        }
    )
    lists_worksheet: str = ""
    header_row: int = 3
    data_start_row: int = 4
    formula_columns: list[str] = Field(
        default_factory=lambda: [
            "SN",
            "Due date (Approx. 2 weeks)",
            "Server Link",
            "Link Path - 1",
            "Link Path",
        ]
    )
    backup_dir: str = str(BACKUP_DIR)
    mapping: ColumnMapping = Field(default_factory=ColumnMapping)
    closed_statuses: list[str] = Field(default_factory=lambda: ["CLOSED"])
    open_statuses: list[str] = Field(
        default_factory=lambda: ["OPEN", "PLACED", "UNDER NTP", "UNDER GATEPASS", "ON HOLD"]
    )
    status_open_values: list[str] = Field(default_factory=lambda: ["OPEN"])
    placed_statuses: list[str] = Field(default_factory=lambda: ["PLACED"])
    pending_statuses: list[str] = Field(default_factory=lambda: ["OPEN", "UNDER NTP", "ON HOLD"])
    due_offsets: dict[str, int] = Field(
        default_factory=lambda: {
            "direct cash": 3,
            "local po": 5,
            "international": 10,
            "service": 10,
            "consumable": 2,
            "emergency": 0,
            "under warranty": 10,
            "alternative": 10,
        }
    )
    due_offset_default_days: int = 14
    in_progress_statuses: list[str] = Field(default_factory=lambda: ["PLACED", "UNDER GATEPASS"])
    cancelled_statuses: list[str] = Field(default_factory=lambda: [])
    aging_buckets: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {"id": "0-1", "label": "0–1 days", "min": 0, "max": 1},
            {"id": "2-3", "label": "2–3 days", "min": 2, "max": 3},
            {"id": "4-7", "label": "4–7 days", "min": 4, "max": 7},
            {"id": "8-14", "label": "8–14 days", "min": 8, "max": 14},
            {"id": "15-30", "label": "15–30 days", "min": 15, "max": 30},
            {"id": "31-60", "label": "31–60 days", "min": 31, "max": 60},
            {"id": "60+", "label": "60+ days", "min": 61, "max": None},
        ]
    )
    require_closed_date_on_close: bool = False
    allow_close_before_create: bool = False
    allow_open_with_close_date: bool = True
    jwt_secret: str = "woms-dev-secret-change-in-production-2026"
    jwt_expire_hours: int = 12
    auto_refresh_seconds: int = 60
    id_prefix: str = "MR"
    permissions: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "admin": [
                "view",
                "edit",
                "create",
                "delete",
                "reports",
                "analytics",
                "settings",
                "users",
                "audit",
                "backup",
            ],
            "manager": ["view", "edit", "create", "reports", "analytics", "audit"],
            "user": ["view", "edit", "reports"],
            "readonly": ["view", "reports", "analytics"],
            "guest": ["view"],
        }
    )


def default_config() -> AppConfig:
    return AppConfig()


def resolve_excel_path(configured: str = "") -> Path:
    """Find file.xlsx even if a saved config points at another machine."""
    candidates: list[Path] = []
    if configured:
        p = Path(configured)
        candidates.append(p if p.is_absolute() else (ROOT / p))
    candidates.extend(
        [
            ROOT / "file.xlsx",
            Path.cwd() / "file.xlsx",
            Path.cwd().parent / "file.xlsx",
            ROOT.parent / "file.xlsx",
        ]
    )
    seen: set[str] = set()
    for c in candidates:
        try:
            key = str(c)
            if key in seen:
                continue
            seen.add(key)
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    return (ROOT / "file.xlsx").resolve()


_CFG: Optional[AppConfig] = None
_CFG_MTIME: Optional[float] = None
_DEFAULT_JWT = "woms-dev-secret-change-in-production-2026"


def _persistent_jwt_secret(configured: str) -> str:
    env = (os.environ.get("WOMS_JWT_SECRET") or "").strip()
    if env:
        return env
    if configured and configured != _DEFAULT_JWT:
        return configured
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / ".jwt_secret"
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    secret = secrets.token_urlsafe(48)
    path.write_text(secret, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return secret


def invalidate_config_cache() -> None:
    global _CFG, _CFG_MTIME
    _CFG = None
    _CFG_MTIME = None


def load_config() -> AppConfig:
    global _CFG, _CFG_MTIME
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    mt = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0.0
    if _CFG is not None and _CFG_MTIME == mt:
        return _CFG
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cfg = AppConfig.model_validate(data)
    else:
        cfg = AppConfig()
    found = resolve_excel_path(cfg.excel_path)
    if found.exists() and str(found) != cfg.excel_path:
        cfg.excel_path = str(found)
    elif not Path(cfg.excel_path).exists() and found.exists():
        cfg.excel_path = str(found)
    cfg.jwt_secret = _persistent_jwt_secret(cfg.jwt_secret)
    _CFG = cfg
    _CFG_MTIME = mt
    return cfg


def save_config(cfg: AppConfig) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    invalidate_config_cache()
