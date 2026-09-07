# SKILLS.md — Linkco MR / WOMS (AI operating manual)

**This is the living skills, requirements, and architecture file for AI and humans.**

If you change product behavior, data flow, APIs, permissions, Excel handling, backup, tour, or tests, **update this file in the same commit** and push it to GitHub. Do not leave a second unofficial “notes” file. `README.md` and `docs/EXCEL_ANALYSIS.md` must stay consistent with the Source of truth section below.

Last updated: 2026-09-07 (backup download/upload-restore + recovery commands).

---

## 1. What this project is

Production operations dashboard for **Linkco (Al Rawabet Commercial Services and Contracting Co. W.L.L.)** material requests (MRs) tied to IM work orders.

Product name in the UI: **Linkco MR**. Code / repo: `excel-dashboard` / **WOMS**.

It is a **fully functional application**, not a mockup. Statistics are counted from live records. Never invent sample KPIs.

Daily path: **Queue → open an MR → update → Save**.

---

## 2. How an AI must work here

1. Read this file before coding.
2. Inspect the real workbook (`file.xlsx`) and current code. Do not assume Excel column names.
3. Explain structure + plan when the change is large, then implement.
4. Do not ask the user to redesign Excel unless absolutely necessary.
5. After the change: tests that cover the new behavior, frontend build if UI changed, **edit this file**, commit, push the session branch.
6. Never force-push. Never commit `file.xlsx` unless the user explicitly asked to change the workbook. Never commit `data/woms.db` or `data/app_config.json`.

### Before-you-code checklist

- [ ] Does this violate Source of truth (DB first)?
- [ ] Will Excel formulas / report sheets / original columns be touched?
- [ ] Could this create duplicate MRs for the same row identity?
- [ ] Are statuses / headers coming from config or live data, not hard-coded?
- [ ] Is backup/write still: backup → write temp → validate → atomic replace, with file lock?
- [ ] Did you update **this file** if behavior changed?

---

## 3. Source of truth (non-negotiable)

**SQLite (`data/woms.db`) is the live work-order history.**

**`file.xlsx` is a replica** written after a successful database save, plus a snapshot target for Backup now / autobackup.

```
UI  →  FastAPI  →  SQLite (commit)  →  copy row into file.xlsx
                     ↑
              boot seed if empty
```

| Action | Correct behavior |
| ------ | ---------------- |
| List / KPIs / search | Read `wo_cache` (and related SQLite tables). Not Excel. |
| Save / create / delete / bulk | Write SQLite first. Then attempt Excel. |
| Excel locked / missing / failed | Keep the DB row. Return `_excel_backup_ok: false` and the error. Never roll back the database because Excel failed. |
| Refresh (`force=True` / hard refresh) | Seed from Excel **only when asked** (admin Seed, Upload-then-seed, boot if DB empty). Ordinary load does **not** overwrite SQLite from Excel. |
| `load(force=False)` | Serve DB cache. If empty, seed from Excel once. |
| `load(force=True)` | Seed from Excel into SQLite. |
| Import | Match existing rows by unique identity; do not insert duplicates. |
| Conflict | HTTP 409 + warning. Never silent overwrite. |

**Do not revert this.** An older README that says “Excel is the single source of truth” is obsolete.

---

## 4. Hard requirements

### Excel workbook

- Do **not** redesign `file.xlsx`. Preserve original columns, formulas, formatting, tables, sheet structure, KPI rows 1–2, report sheets.
- Do **not** assume header names. Map via `AppConfig.mapping` / Settings wizard / `data/app_config.json`.
- Header row = 3, data from row 4 (configurable).
- Never overwrite formula columns: SN, due date, Server Link / Link Path (see `formula_columns`).
- Never write report sheets (`SH1 & SH5 - REPORT`, `F5 - REPORT`) or path sheets.
- Never insert/shift columns. Missing mapped headers may be **appended** at the end only (`_ensure_mapped_headers`).
- Identity for a row: `record_id` = `{site_label}:{excel_row}` e.g. `SH5-SH1:13`. **IM Work Order # is not unique** (several MRs per IM WO). Sync by record_id; on import, match by record_id then WO#+site.
- Site (`department`) comes from the worksheet label, not a department column.
- Write path: **file lock → backup (Excel-only for per-save) → temp xlsx → validate opens → `os.replace`**.
- File lock required. HTTP **423** if locked, **503** if missing, **409** on sync-token conflict.

### Database / admin

- Live path: `data/woms.db`. Schema in `backend/app/database.py` (`SCHEMA` + `init_db` migrations).
- Admin **Reset database**: wipe users, chat, settings, attachments, work orders; recreate schema + default logins via `init_db`; then seed from current/uploaded Excel. Confirm body must be exactly `DELETE`.
- **Do not delete `app_config.json`** on reset (column mapping lives there).
- Default logins after reset / empty DB:

  | Username | Password    | Role    |
  | -------- | ----------- | ------- |
  | admin    | admin123    | admin   |
  | manager  | manager123  | manager |
  | user     | user123     | user    |

### Product rules

- Calculate statistics dynamically from live records (`backend/app/stats.py`, `domain.py`). No fake numbers.
- Do not hard-code statuses if Excel/DB/config has different values. Business rules are configurable (`closed_statuses`, `pending_statuses`, delay rules, due offsets, required fields, field-edit roles).
- Conflicts: show a warning; user reloads or force-overwrites.
- Deliver a working app, not a prototype.

### Security / preview

- Keep `X-Frame-Options: SAMEORIGIN` (sandbox live preview). Do not switch to `DENY`.
- Bind servers to `0.0.0.0`. Vite already `allowedHosts: true` and proxies `/api` to the backend. Browser code must use relative `/api` URLs, never `localhost`.
- Change `jwt_secret` in production (`WOMS_JWT_SECRET` or `data/.jwt_secret`).

### Python

- Python 3.11+ (3.11–3.13 recommended). **Pydantic ≥ 2.12** for 3.14 wheels. Do **not** pin pydantic 2.9.x (pydantic-core/PyO3 maxes out at 3.13).
- `backend/requirements.txt` is the pin surface.

---

## 5. Excel workbook structure

Inspected live file: repo-root `file.xlsx`. Details: `docs/EXCEL_ANALYSIS.md`.

| Sheet | Role |
| ----- | ---- |
| `Linkco_MR_Log (SH5 & SH1)` | Data — Shield 5 & Shield 1. Site label `SH5-SH1`. Table `Table1`. |
| `Linkco_MR_Log (F5)` | Data — Falcon 5. Site label `F5`. IDs like `LKF5-nnnn`. |
| `Linkco_MR_Log (Office)` / `(Accommodations)` | Extra sites if present. |
| `SH1 & SH5 - REPORT`, `F5 - REPORT` | Reports — **never written**. |
| `File Pah` / `File Pah (F5)` | UNC paths for hyperlink formulas — **never written**. |

Default mapping (Excel header → internal field):

| Excel | Field | Notes |
| ----- | ----- | ----- |
| IM Work Order # | `work_order_id` | Not unique |
| WO Priority Level | `priority` | |
| IM WO Completion | `completion_date` | |
| MR Received Date | `created_date` | |
| Assign to | `assigned_to` | |
| Purchase Type | `work_type` | drives due-date offset |
| Due date (Approx. 2 weeks) | `due_date` | formula; app computes display, never writes |
| WO Asset Name | `location` | |
| Required Material Details | `description` | |
| STATUS | `status` | OPEN, PLACED, CLOSED, UNDER NTP, UNDER GATEPASS, ON HOLD, … |
| Date of PO / Expected PO / RFQ Sent | `scheduled_date` | |
| Supplier Name | `supplier` | |
| ETA / Expected Date of RFQ Response | `closed_date` | ETA / close proxy |
| Delivery Status | `issue` / `delay_reason` | |
| REMARKS / NOTES | `remarks` | |
| PO NO # | `po_number` | |
| Delay Type / Source / Justification | `delay_kind` / `delay_source` / `delay_justification` | appended if missing |

Due offsets (purchase type, days): Direct Cash 3, Local PO 5, International/Service/Warranty/Alternative 10, Consumable 2, Emergency 0, else `due_offset_default_days` (14).

---

## 6. Layout (code)

```
backend/app/                 FastAPI app
  main.py                    Boot, seed if DB empty, autobackup scheduler, SPA, security headers
  config.py                  AppConfig, mapping, resolve_excel_path, jwt
  database.py                SQLite schema, users, wo_cache, collab, snapshot_to / restore_from
  excel/service.py           DB-first CRUD + Excel replica + backups
  backup.py                  Autobackup schedule
  domain.py / stats.py       Flags, filters, KPIs
  security.py                JWT, roles, field-edit roles
  routers/                   auth, work_orders, dashboard, ops, catalog, collab, settings, …
frontend/src/
  pages/                     Dashboard, WorkOrders, WorkOrderDetail, Queue, Settings, Guide, …
  components/Tour.jsx        First-run tour overlay
  lib/tour.js                TOUR_STEPS v1
  context/                   Auth, Ui (ask/toast), Tour, Theme
data/                        woms.db, app_config.json, attachments/  (gitignored except examples)
file.xlsx                    Live workbook at repo root — do not clobber in tests
tests/                       pytest
docs/EXCEL_ANALYSIS.md       Workbook inspection
docs/RECOVERY.md             Data loss / Docker / restore / admin commands
scripts/recover.sh           Host file check + command cheat sheet
scripts/reset_admin.py       Reset or create admin login
SKILLS.md                    This file
```

Boot (`main._boot`): `init_db()`. If `wo_cache` is empty and Excel exists → `seed_from_excel(replace_lines=True)`. Else `excel_service.load()` from DB.

---

## 7. Save / Excel replica implementation

`ExcelService` (`backend/app/excel/service.py`):

- `get_all()` / `load()` → SQLite `wo_cache`.
- `update_record` / `update_records` / `create_record` / `delete_record` → SQLite first, then `_excel_*`.
- `_excel_update_record` etc. copy Excel with reason `update` / `bulk` / `create` / `delete` / `import` / `upload` / `reconcile` (**Excel-only**, no SQLite snapshot).
- On Excel failure the DB row stays; response includes `_excel_backup_ok` / `_excel_backup_error`.
- `seed_from_excel` reads the workbook and `replace_wo_cache`.
- `replace_from_bytes` replaces live Excel then seeds.

`resolve_excel_path`: if the configured path is not a file, substitute existing `ROOT/file.xlsx`. **Tests must not use `save_config(excel_path=missing.xlsx)` to simulate a missing workbook** — that still resolves to `file.xlsx` and can overwrite the real file. Stub `_excel_update_record` or `available()` instead. Always restore `file.xlsx` if a test hits it.

---

## 8. Backup / restore

Two different kinds of copies:

### A. Write-safety (every Excel write)

Reasons: `update`, `create`, `delete`, `bulk`, `import`, `upload`, `reconcile`.

- Copy **Excel only** to `{backup_dir}/{YYYY-MM-DD}/{stem}_{ts}_{reason}.xlsx`.
- Not a SQLite snapshot.

### B. Snapshots (Backup now, autobackup, pre-restore)

Reasons in `ExcelService.SNAPSHOT_REASONS`: `manual`, `auto`, `pre_restore`.

- Pair: same stem/timestamp `.xlsx` **and** `.db` via `database.snapshot_to` (sqlite3 backup API).
- If Excel is missing, still snapshot SQLite (`woms_{ts}_{reason}.db`) and list that unpaired `.db`.
- Autobackup no longer skips when Excel is unavailable.

### Restore

- If sibling `.db` exists (or the item is a `.db`): restore **database + Excel**. Pre-restore snapshot is taken first.
- If Excel-only: replace `file.xlsx` only. **Do not silently seed/overwrite SQLite.** Operator must Seed from Excel if they want those rows.
- Settings UI: DB column, different confirm copy, `data-tour="backup"`.
- Health: backup row count (Excel and/or `wo_cache` in the `.db`) vs live DB count. Fail if backup has &lt; 50% of live rows.
- Prune (`backup_ratio`, default keep last 14 auto/manual): deletes paired `.db` with the `.xlsx`. Write-safety copies are not pruned.
- **Download** (`GET /api/settings/backups/download?path=`): zip of `.xlsx`+`.db` when paired, otherwise the single file.
- **Upload & restore**: `POST /api/settings/backups/upload` accepts `.xlsx` / `.xlsm` / `.db` / zip of both. Saves into the backup folder (does not replace live data by itself). UI then prompts Restore. Restore of a pair rolls SQLite + Excel; Excel-only does not seed the database.
- Operator commands: `docs/RECOVERY.md`, `scripts/recover.sh`, `scripts/reset_admin.py`. Docker down does **not** delete host `data/` or `backups/` (bind mounts).

Scheduler: `backend/app/backup.py`, 20s loop, `backup_auto_enabled`, `backup_time`, `backup_days` (0=Mon … 6=Sun), `backup_start_date`.

---

## 9. Auth, roles, pages

Permissions: `view`, `edit`, `create`, `delete`, `reports`, `analytics`, `settings`, `users`, `audit`, `backup`, plus page keys (`queue`, `materials`, …).

Default role grants (`config.permissions` / frontend `ROLE_PERMS`):

| Role | Can |
| ---- | --- |
| admin | everything |
| manager | view, edit, create, reports, analytics, audit |
| user | view, edit, reports |
| readonly | view, reports, analytics |
| guest | view + explicitly granted pages |

`field_edit_roles` (default): `supplier` and `po_number` → admin, manager. Admin always can. Unlisted fields: anyone with `edit`.

Status-change remarks (default): `*->ON HOLD`, `*->CLOSED`.

PLACED requires `po_number` by default (`status_required_fields`).

---

## 10. Frontend

- React + Vite + Tailwind. Dev: `0.0.0.0:5173`, proxy `/api` → `127.0.0.1:8000`.
- Production: `npm run build` → FastAPI serves `frontend/dist` when present.
- Confirmations: `UiContext.ask()` (restore, seed, reset, retry). Toasts for success/errors.
- Header: Search, Refresh, Live|Offline. `?` opens `/guide` unless a tour is active.
- Work-order list columns persist in `localStorage["woms.columns"]`.
- Work order editor tabs: Details / Suppliers / Activity.
- Filters start collapsed; chips remove filters.
- After Settings StrReplace, **assert `function DatabasePanel` still exists** if you insert `<DatabasePanel />` (vite can build while runtime ReferenceError).

### Tour / Guide

- `TOUR_VERSION = "v1"`. Key: `localStorage["woms.tour.v1:"+username] = "done"`.
- **Do not bump `TOUR_VERSION`** just to add a step. Replay from Guide / Account / header help shows new steps.
- First-run auto-start (~800ms) re-checks `tourSeen` so Skip does not restart.
- `measureTarget` must pick a **visible** `[data-tour]` (desktop vs mobile sidebar).
- Overlay click does **not** skip. Esc skips.
- Current `data-tour` ids: `nav-work`, `search`, `live`, `dashboard`, `wo-list`, `filters`, `wo-new`, `wo-tabs`, `wo-save`, `queue`, `backup`.
- Admin backup step: `need: "backup"`, `page: "settings"`, target `backup`.

---

## 11. API map (prefixes)

| Prefix | Purpose |
| ------ | ------- |
| `/api/health` | Liveness + record count |
| `/api/auth` | login, me, logout |
| `/api/work-orders` | list, CRUD, bulk, claim, watch, chat, timeline, seen, PDF sheet |
| `/api/dashboard` | KPIs / charts from live records |
| `/api/ops` | queue, digest, alerts, handover, health scan |
| `/api/catalog` | suppliers, materials, aliases, MR lines |
| `/api/collab` | chat, projects, notifications, saved views |
| `/api/files` | attachments |
| `/api/reports` | Excel/CSV/PDF reports |
| `/api/audit` | field-level audit log |
| `/api/users` | user admin |
| `/api/settings` | config, mapping scan, backups, database seed/reset/upload |
| `/api/sync` | ping, refresh (`hard: true` seeds) |

HTTP: 400 validation, 403 permission, 409 conflict, 422 business rules, 423 Excel locked, 503 Excel unavailable.

---

## 12. Tests

```bash
python3 -m pytest tests -q
cd frontend && npm run build
```

| File | Covers |
| ---- | ------ |
| `tests/test_database_sot.py` | DB-first save, seed/reset confirm, snapshot pair + Excel-only restore, download zip + upload + restore |
| `tests/test_excel_and_api.py` | Read/write Excel, backup schedule/prune |
| `tests/test_ops_pack.py` | Queue, digest, timeline, mapping, backup health |
| `tests/test_collab_*.py` | Chat, watches, row restore |
| `tests/test_materials_catalog.py` | Lines, aliases |
| `tests/test_delay_sites.py` | Extra sites / delay rules |

Pitfalls (do not repeat):

- `save_config(excel_path=missing.xlsx)` does **not** make Excel unavailable (`resolve_excel_path` falls back to `file.xlsx`). Stub `_excel_update_record`.
- Do not leave `file.xlsx` modified. Workbook fixtures copy to `tmp_path` and restore config `excel_path` / `backup_dir`.
- `text.replace("    def create_record(\n"` misses one-line defs.
- Sequential StrReplace on a stale `database.py` snapshot fails; re-read the file.
- Tests share `data/woms.db`. Prefer fixture seed (`get_all(force=True)`) over assuming empty.

---

## 13. Git / GitHub

- Session branch only: `arena/01a07168-excel-dashboard`. Do not switch, rename, or push other branches.
- Push: `git push origin arena/01a07168-excel-dashboard`. Never force-push.
- Do not commit: `data/woms.db`, `data/app_config.json`, `data/.jwt_secret`, `data/attachments/`, `backups/`, `frontend/dist`, `node_modules`, `.venv`.
- `file.xlsx` is in the repo; do not rewrite it as a side effect of tests or mapping experiments.

Shipped milestones (do not regress):

| Commit | What |
| ------ | ---- |
| `fe9c21c` | Multi-supplier lines, material search, aliases |
| `aef7883` | Database as work-order history, Excel as save backup |
| `abdf576` | Daily-path UI (compact filters, tabbed WO, quieter chrome) |
| `feb7b71` | First-run tour + Guide |
| `dc7bc07` | Snapshot SQLite with Excel on Backup now / autobackup |

---

## 14. Playbook — common change types

### New mapped Excel column

1. Add field on `ColumnMapping` with the **real header** (or empty until Settings maps it).
2. Do not rename the Excel header.
3. If it is a formula, add it to `formula_columns` and never write it.
4. If it may be missing, append-only via `_ensure_mapped_headers`.
5. Update Settings mapping wizard + this file.

### New work-order behavior (claim, remarks, status)

1. Configurable rules in `AppConfig`, not hard-coded status lists.
2. Validate in `validation.py` / router.
3. Write DB first, Excel second.
4. Audit via `database.add_audit`. Notify watchers if it is a user-visible change.

### New Settings / admin action

1. Gate with `require_permission`.
2. Destructive actions use `UiContext.ask()` and an explicit confirm string when wiping data (`DELETE`).
3. Keep `app_config.json` on database reset.

### New tour step

1. Add `data-tour="…"` on a **stable, visible** node.
2. Append a step in `frontend/src/lib/tour.js`. Do **not** bump `TOUR_VERSION`.
3. Mention it on Guide if it is operator-facing.

### Backup behavior

1. Per-save reasons stay Excel-only.
2. Snapshot reasons (`manual` / `auto` / `pre_restore`) pair `.xlsx` + `.db`.
3. Restore: pair → both; Excel-only → Excel only, no silent seed.
4. Download zips the pair. Upload accepts `.xlsx` / `.db` / zip into the backup folder, then the UI prompts Restore.
5. Operator recovery lives in `docs/RECOVERY.md` — do not bury commands only in chat.

---

## 15. Requirements backlog (product)

Must remain true:

- [x] Database is live MR history; Excel is replica + snapshot
- [x] Configurable column mapping; original Excel preserved
- [x] No duplicate rows on sync; match by identity
- [x] Conflict warning, not silent overwrite
- [x] File lock + backup + validate + atomic replace for Excel writes
- [x] Dynamic statistics
- [x] Configurable statuses / due offsets / field roles
- [x] Admin seed / upload-then-seed / reset (`DELETE`), keep mapping
- [x] Backup now + autobackup snapshot SQLite + Excel
- [x] First-run tour + in-app Guide
- [x] Default users recreated after reset
- [x] Download / upload / restore snapshots (xlsx, db, zip)
- [x] Recovery commands (`docs/RECOVERY.md`)

When you complete or change a requirement, tick/retarget it here.

---

## 16. Decision log (append, do not rewrite history)

AI: add a bullet when you make a lasting decision. Date + short why.

- **2026-09 (aef7883)** Excel is no longer SoT. User reversed earlier Excel-SoT. DB first, Excel copy on save. Excel failure keeps DB.
- **2026-09** Admin reset wipes **everything** (users, chat, settings, WOs), then new DB + seed. Recreate default logins. Keep `app_config.json`.
- **2026-09 (dc7bc07)** Snapshots (`manual`/`auto`/`pre_restore`) pair `.xlsx`+`.db`. Per-save copies stay Excel-only. Excel-only restore does not seed DB.
- **2026-09 (feb7b71)** Tour v1; replay instead of bumping version when adding steps. Overlay click does not skip.
- **2026-09** `X-Frame-Options: SAMEORIGIN` required for preview. Do not set `DENY`.
- **2026-09** Pydantic ≥ 2.12 for Python 3.14; do not pin 2.9.x.
- **2026-09** Backup UI: Download (zip pair), Upload & restore (.xlsx/.db/zip). Recovery commands in `docs/RECOVERY.md`.
