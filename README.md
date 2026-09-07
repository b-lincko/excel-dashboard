# Work Order Management System (WOMS)

A production-ready operations dashboard for **Linkco’s Material Request / IM Work Order log**.

**SQLite (`data/woms.db`) is the live work-order history.** `file.xlsx` is a replica written after each save, and a snapshot target for Backup now / autobackup.

The application:

1. Serves material requests from the database
2. Displays KPIs, analytics and a searchable table counted from live records
3. Lets authorized users edit records (database first)
4. Copies each successful save into the **same Excel workbook** as a backup replica
5. Seeds the database from Excel on first boot (empty DB), or when an admin chooses Seed / Upload-then-seed
6. Calculates statistics dynamically — no fake or stored KPI tables

```
React dashboard  ⇄  FastAPI  ⇄  SQLite (history)
                         ↘ file.xlsx (replica + snapshots)
```

**AI / contributors:** read and update [`SKILLS.md`](SKILLS.md) whenever behavior changes. Also [`AGENTS.md`](AGENTS.md) and [`docs/EXCEL_ANALYSIS.md`](docs/EXCEL_ANALYSIS.md).

**Data loss / Docker down:** [`docs/RECOVERY.md`](docs/RECOVERY.md) — find the database, restore snapshots, reset admin. Quick check: `./scripts/recover.sh`.

## Quick start

### One command

**Docker (recommended)** — installs Docker if missing, builds the image, serves API + UI on port 8000:

```bash
chmod +x docker-run.sh run.sh
./docker-run.sh
```

Windows: double-click `docker-run.bat`.

**Linux / macOS without forcing Docker**

```bash
chmod +x run.sh
./run.sh
```

`./run.sh` uses Docker when it can; `./run.sh --local` installs Python/Node on the host instead.

**Windows (host Python + Node)**

Double-click `run.bat`, or from Command Prompt:

```bat
run.bat
```

Local mode installs Python packages into `.venv`, runs `npm install` if needed, then starts:

- API — http://127.0.0.1:8000
- UI — http://127.0.0.1:5173  (Docker serves both at http://127.0.0.1:8000)

Keep `file.xlsx` in the project root (replica of the live log; the database is the working history).

### Requirements

- Python 3.11+ (3.11–3.13 recommended; 3.14 is supported via current Pydantic wheels)
- Node.js 18+

### Manual install

### 1. Install backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Generate / use the Excel workbook

The live workbook is **`file.xlsx`** at the repo root (Linkco MR logs for Shield 5 / Shield 1 and Falcon 5).

Column mapping is in Settings / `data/app_config.json`. Excel headers are not renamed. Formula columns (SN, due date, hyperlinks) and the report sheets are never overwritten.

See `docs/EXCEL_ANALYSIS.md` for the inspected structure.

### 3. Install frontend

```bash
cd frontend
npm install
```

### 4. Run

Terminal A — API (binds `0.0.0.0:8000`):

```bash
cd backend
source .venv/bin/activate
python run.py
```

Terminal B — UI (binds `0.0.0.0:5173`, proxies `/api` to the backend):

```bash
cd frontend
npm run dev
```

Open the UI, then sign in:

| Username | Password   | Role    |
| -------- | ---------- | ------- |
| admin    | admin123   | Admin   |
| manager  | manager123 | Manager |
| user     | user123    | User    |

## What the dashboard does

- **KPIs** — total, open, closed, pending, overdue, in progress, completion rate, average closing time, aging
- **Time windows** — today, yesterday, this/last week, this/last month, quarter, year, custom range
- **Weekly / monthly / yearly** analysis with year-over-year comparison
- **Status distribution** from live record values (not hard-coded)
- **Why are work orders still open?** — grouped by Delay Reason / Issue, click to drill down
- **Aging buckets** — 0–1, 2–3, 4–7, 8–14, 15–30, 31–60, 60+ days
- **Overdue** list sorted by days overdue and priority
- **Department, technician, priority** performance tables
- **Work order table** — search, sort, filter, pagination, column visibility, CSV export, inline drill-down
- **Edit** — Save writes SQLite first, then copies the row into Excel; if Excel is locked the record is still kept
- **Audit log** — user, time, work order, field, old/new value (SQLite)
- **Backups** — per-save Excel copies under the admin-selected folder (`backups/YYYY-MM-DD/`); Backup now / autobackup also snapshot SQLite as a paired `.db`. Restore of a pair rolls both back; Excel-only copies do not overwrite live history
- **Conflict detection** — if Excel changed since you loaded the record, you get a warning instead of a silent overwrite
- **Reports** — daily/weekly/monthly/yearly, open/overdue/closed/delay/department/technician as Excel, CSV or PDF
- **Auth** — admin / manager / user with configurable permissions
- **Dark / light** theme

## Database and Excel

| Action | Behaviour |
| ------ | --------- |
| Ordinary load / Refresh | Reads SQLite. Does not overwrite the database from Excel. |
| Hard refresh / Seed | Admin (or boot if DB empty) copies Excel rows into SQLite. |
| Save | SQLite commit, then Excel: backup → temp file → validate → atomic replace |
| File locked | Record stays in the database. HTTP 423 on the Excel replica. |
| File missing | Record stays in the database. HTTP 503 on Excel-only operations. |
| External Excel change during an Excel write | HTTP 409 conflict; user can reload or force overwrite |
| Backup now / autobackup | Snapshot SQLite + Excel as a pair |
| Restore paired snapshot | Rolls back database and Excel (pre-restore snapshot first) |
| Restore Excel-only copy | Replaces `file.xlsx` only. Does not silently seed the database. |

Formulas, report sheets, lists, formatting and Excel tables are preserved. Only mapped data cells on the log sheets are updated.

## Configuration

Administrators can change (Settings page or `data/app_config.json`):

- Excel file path and worksheet name
- Column mapping (Excel header ↔ internal field)
- Which statuses count as closed / pending / in progress
- Aging buckets
- Validation rules
- Backup directory
- Refresh interval

## Tests

```bash
cd /path/to/excel-dashboard
python3 -m pytest tests -q
```

Coverage includes reading Excel, uniqueness, KPI calculations, updating a row, rejecting duplicates, date validation, authentication and formula preservation.

## Production notes

- Change `jwt_secret` in Settings before exposing the app
- Serve `frontend` via `npm run build` and let FastAPI host `frontend/dist` (enabled automatically when the folder exists)
- Put the workbook on a filesystem both the API and Excel users can reach
- Keep `backups/` on the same volume or a snapshot target
- Live work orders live in SQLite (`wo_cache`); in-memory cache is invalidated on write. Suitable for tens of thousands of rows

## Project layout

```
backend/app/          FastAPI application
backend/app/excel/    DB-first CRUD, Excel replica, lock, backup, mapping
frontend/src/       React dashboard
file.xlsx           Live workbook (replica)
data/woms.db        Live history (gitignored)
SKILLS.md           AI skills, requirements, architecture (living)
docs/EXCEL_ANALYSIS.md
tests/
```

## Pointing at your own workbook

1. Keep your sheet name (or set it in Settings)
2. Map your headers, for example `WO No` → `work_order_id`, `Date Opened` → `created_date`
3. Restart is not required — Save configuration and click Refresh
4. Do not remove the unique ID column; if you have none, the app can generate `WO-YYYY-NNNNNN`
