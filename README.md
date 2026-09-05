# Work Order Management System (WOMS)

A production-ready operations dashboard for **Linkco’s Material Request / IM Work Order log**. The Excel workbook `file.xlsx` is the **single source of truth**.

The application:

1. Reads work orders from Excel
2. Displays KPIs, analytics and a searchable table
3. Lets authorized users edit records
4. Writes every change back to the **same workbook**
5. Reloads when Excel is changed externally
6. Calculates statistics dynamically (nothing is stored as a second work-order database)

```
Excel  ⇄  FastAPI  ⇄  React dashboard
         SQLite only for users, audit log, settings
```

## Quick start

### One command

**Linux / macOS**

```bash
chmod +x run.sh
./run.sh
```

**Windows**

Double-click `run.bat`, or from Command Prompt:

```bat
run.bat
```

This installs Python packages into `.venv`, runs `npm install` if needed, then starts:

- API — http://127.0.0.1:8000
- UI — http://127.0.0.1:5173

Keep `file.xlsx` in the project root (it is the source of truth).

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
- **Status distribution** from the actual Excel values (not hard-coded)
- **Why are work orders still open?** — grouped by Delay Reason / Issue, click to drill down
- **Aging buckets** — 0–1, 2–3, 4–7, 8–14, 15–30, 31–60, 60+ days
- **Overdue** list sorted by days overdue and priority
- **Department, technician, priority** performance tables
- **Work order table** — search, sort, filter, pagination, column visibility, CSV export, inline drill-down
- **Edit** — Save writes the Excel row, confirms, refreshes stats
- **Audit log** — user, time, work order, field, old/new value (SQLite, not mixed into Excel)
- **Backups** — timestamped copies under `backups/YYYY-MM-DD/` before every write
- **Conflict detection** — if Excel changed since you loaded the record, you get a warning instead of a silent overwrite
- **Reports** — daily/weekly/monthly/yearly, open/overdue/closed/delay/department/technician as Excel, CSV or PDF
- **Auth** — admin / manager / user with configurable permissions
- **Dark / light** theme

## Excel synchronization

| Action | Behaviour |
| ------ | --------- |
| Refresh from Excel | Reloads the workbook (mtime + size fingerprint) |
| Save to Excel | Backup → write temp file → validate it opens → atomic replace |
| File locked | HTTP 423: *Excel file is currently being used by another process…* |
| File missing | HTTP 503: *Excel file is currently unavailable.* |
| External change during edit | HTTP 409 conflict; user can reload or force overwrite |

Formulas, the Summary sheet, Lists, formatting and the Excel table are preserved. Only WorkOrders data cells are updated.

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
- The work-order cache is in-memory and invalidated on write / mtime change; suitable for tens of thousands of rows

## Project layout

```
backend/app/          FastAPI application
backend/app/excel/    Read/write, lock, backup, mapping
frontend/src/       React dashboard
data/work_orders.xlsx
scripts/generate_excel.py
docs/EXCEL_ANALYSIS.md
tests/
```

## Pointing at your own workbook

1. Keep your sheet name (or set it in Settings)
2. Map your headers, for example `WO No` → `work_order_id`, `Date Opened` → `created_date`
3. Restart is not required — Save configuration and click Refresh
4. Do not remove the unique ID column; if you have none, the app can generate `WO-YYYY-NNNNNN`
