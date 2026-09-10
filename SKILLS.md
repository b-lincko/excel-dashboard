# SKILLS.md — Linkco MR / WOMS (AI operating manual)

**This is the living skills, requirements, and architecture file for AI and humans.**

If you change product behavior, data flow, APIs, permissions, Excel handling, backup, tour, or tests, **update this file in the same commit** and push it to GitHub. Do not leave a second unofficial “notes” file. `README.md` and `docs/EXCEL_ANALYSIS.md` must stay consistent with the Source of truth section below.

Last updated: 2026-09-10 (ONE-GO RUNNERS UPDATED for the nginx topology: Dockerfile now = nginx (apt) + uvicorn loopback 8001 in one container (deploy/nginx-docker.conf + docker-entrypoint.sh, dist pre-gzipped at build); docker-run.bat/.ps1/.sh unchanged behavior; LOCAL DEV = uvicorn 127.0.0.1:8001 + Vite 5173 as entry (run.bat/run.ps1/run.sh/scripts/start-api.bat updated).

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

**SQLite (`data/woms.db`) is the only live work-order store.**

**`file.xlsx` is a midnight replica** of all database rows (plus Backup now). Daily create / update / delete do **not** write Excel.

```
UI  →  FastAPI  →  SQLite (commit)
                     ↑
              boot seed if empty
Midnight / Backup now → export DB → file.xlsx  +  snapshot SQLite
```

| Action | Correct behavior |
| ------ | ---------------- |
| List / KPIs / search | Read `wo_cache` (and related SQLite tables). Not Excel. |
| Save / create / delete / bulk | Write **SQLite only**. Skip `_excel_*`. |
| New record id | `{site}:DB-{hex}` e.g. `F5:DB-a1b2c3d4e5f6`. Never rewritten on Excel append. |
| Excel locked / missing | Daily saves still succeed. Export at midnight records a health error and still snapshots SQLite. |
| Midnight / Backup now | `export_database_to_excel()` then `create_backup`. Match Excel by `record_id` then `_row`+sheet; append unmatched DB creates; persist `_row`/`_sheet`; do not mass-delete Excel rows. |
| Archive | Move `.xlsx`/`.xlsm`/`.db` older than `backup_archive_days` (30) into `backups/archive/YYYY-MM/`. Delete archives older than `backup_archive_keep_days` (180). |
| Refresh (`force=True` / hard refresh) | Seed from Excel **only when asked** (admin Seed, Upload-then-seed, boot if DB empty). Ordinary load does **not** overwrite SQLite from Excel. **Do not `get_all(force=True)` after a DB-only create** — that reseeds and drops the new row. |
| `load(force=False)` | Serve DB cache. If empty, seed from Excel once. |
| `load(force=True)` | Seed from Excel into SQLite. |
| Import / reconcile / upload | Still write Excel (not daily create-order). |
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
- Site (`department`) comes from the worksheet label, not a department column. **Camp sites** (SH5 Site - 1/2/3/4A/5/7, SH1 L1/L2/L3/L4/L5/L7/LS1/LS2) are **not** extra Excel tabs and must not be stored as `department` (that would retarget `resolve_data_sheet`). Infer from `WO Asset Name` prefixes; persist `camp_site` in SQLite only. Filter `department=SH5-S1` / `Site - 1` / `SH5` matches the camp, not a new sheet.
- Excel dump / import write path: **file lock → temp xlsx → validate opens → `os.replace`**. If `os.replace` raises EBUSY/ETXTBSY (Docker bind-mounted `file.xlsx`), copy bytes into the existing inode (`_replace_excel_file`) so Upload Excel then seed still works. Daily CRUD does not take this path.
- File lock required. HTTP **423** if locked, **503** if missing, **409** on sync-token conflict.

### Database / admin

- Live path: `data/woms.db`. Schema in `backend/app/database.py` (`SCHEMA` + `init_db` migrations). Connections use WAL + `busy_timeout=15000` + `cache_size`/`mmap` so several people can save at once.
- Excel seed (`seed_from_excel(replace_lines=True)`) writes `wo_cache` then `bulk_seed_catalog` (one transaction, `executemany`). Do **not** call `replace_mr_lines` per row on upload.
- Admin **Reset database**: wipe users, chat, settings, attachments, work orders; recreate schema + default logins via `init_db`; then seed from current/uploaded Excel. Confirm body must be exactly `DELETE`.
- **Do not delete `app_config.json`** on reset (column mapping lives there).
- Default logins after reset / empty DB (UI and API block other work until that user sets a new password; pytest skips the block via `PYTEST_CURRENT_TEST`):

  | Username | Password    | Role    |
  | -------- | ----------- | ------- |
  | admin    | admin123    | admin   |
  | manager  | manager123  | manager |
  | user     | user123     | user    |

  Technicians (seeded by `TEAM_USERS` on every `init_db` if missing; survive admin reset). Temporary passwords must be changed:

  | Username | Password      | Assign to name |
  | -------- | ------------- | -------------- |
  | abubacar | abubacar1234  | Abubacar       |
  | arun     | arun1234      | Arun           |
  | nesar    | nesar1234     | Nesar          |
  | yousuf   | yousuf1234    | Yousuf         |

  **Assign to** is technicians only: active users with `role=user` (Abubacar, Arun, Nesar, Yousuf, plus any new User-role login). **Not** admin or manager. The current name stays visible if it is already on the MR. Create / save / bulk that changes Assign to sends an inbox ping (`kind=assign`) to that login. Claim is also technicians-only.

### Product rules

- Calculate statistics dynamically from live records (`backend/app/stats.py`, `domain.py`). No fake numbers.
- **Priority charts/filters** collapse case (`LOW`/`Low` → `Low`, `MEDIUM`/`Medium` → `Medium`) via `canonical_priority`. Do not invent extra priority values.
- **Open KPI / `/open`** = `is_status_open` (STATUS token `open`, including `OPEN.` / extra spaces). Excel rows with a STATUS but a blank IM WO # are still seeded so the count matches the workbook.
- **Blockades KPI / pie / mind map** = `is_blockade`: outstanding statuses that are **not OPEN, not PLACED, not CLOSED** (NTP, hold, gatepass, pending, …). Filter flag `blockade`. Do not count OPEN or PLACED as blockades.
- Do not hard-code statuses if Excel/DB/config has different values. Business rules are configurable (`closed_statuses`, `pending_statuses`, delay rules, due offsets, required fields, field-edit roles).
- Conflicts: show a warning; user reloads or force-overwrites.
- Deliver a working app, not a prototype.

### Security / preview

- Keep `X-Frame-Options: SAMEORIGIN` (sandbox live preview). Do not switch to `DENY`.
- Bind servers to `0.0.0.0`. Vite already `allowedHosts: true` and proxies `/api` to the backend. Browser code must use relative `/api` URLs, never `localhost`.
- Change `jwt_secret` in production (`WOMS_JWT_SECRET` or `data/.jwt_secret`). Settings GET/PUT never return `jwt_secret`, `smtp_password`, or `resend_api_key`.
- Login lockout: 8 failed attempts / 10 minutes per username+IP (`429`).
- Unhandled API errors return `Internal server error` unless `WOMS_DEBUG=1`.
- Attachment download/delete must resolve inside `data/attachments/`.
- New user passwords min 8 characters. Default logins must change password (`must_change_password`) before other API calls. Logout revokes the JWT `jti`. Extra grants cannot include `users`, `settings`, or `backup`.
- Operator training slides: `docs/training/index.html`.

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
| *(no extra tabs)* | SH5 camps Site - 1/2/3/4A/5/7 and SH1 L1–L7 / LS1 / LS2 live **on** `SH5-SH1`. |
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

Due offsets (purchase type, days): Direct Cash 3, Local PO 5, International/Service/Warranty/Alternative 10, Consumable 2, Emergency 0, else `due_offset_default_days` (14). **If Purchase type is empty**, do **not** apply the 14-day default — the operator picks a **date-only** due date and save must send `due_date`. `_apply_due_date` skips empty `work_type`.

**Overdue:** OPEN / PENDING still use purchase-type due date (`is_delayed`). **PLACED overdue uses ETA (`closed_date`)**, not due date. Do not treat PLACED past due_date as overdue. `is_delayed` stays the delay-notes flag (OPEN past due / PENDING) and is **not** aliased to `is_overdue`.

**Close order prices** (`unit_price`, `price`, `total_price`, `final_price`) live in SQLite (`wo_cache` payload + `mr_lines.unit_price`). They are **not** Excel columns. `_merge_mapped` allow-lists them; midnight Excel dump does not write them.

**PO digital signature** (`backend/app/approvals.py`, tables `po_approvals` / `po_approval_events`):

**PDF signature embed:** `_signature_image` in `reports.py` decodes the base64 PNG and prints it at corporate size (max 80×28 mm, aspect kept) above a signature line + signer + timestamp. **reportlab 5.x gotchas (both fixed 2026-09-10, regression-tested):** `platypus.Image` must receive a `BytesIO`, not an `ImageReader` (TypeError was swallowed by the silent except → signed slips printed "No signature on file yet"), and `HRFlowable` widths inside table cells must be numeric mm (`80 * mm`), not the string `"80mm"`.

Dedicated page **`/approvals`** (Daily nav **Purchase Approval**, `g then p`). Guest page key `po_approvals`.

1. Dispatcher assigns a technician (or **Unassign**).
2. Technician sends the PDF to **1–3 managers** (`managers` column).
3. A selected manager **must digital-sign**. The signature prints on the PDF at corporate size (~80×28 mm, aspect kept). They then send the signed slip back to the sender or someone else (`holder`).
4. The holder (or dispatcher) sends it to **Accounts** or another person (`POST .../approval/route`).
5. Approve **locks** PO fields. Extra grants: `po_dispatch`, `po_approve`, `accounts`.
   - Routes on the WO router: `GET /{id}/approval`, `POST .../assign`, `POST .../submit` (body `{managers: []}` — **the picked list is honored**), `POST .../unassign` (dispatcher only, not from locked states), `POST .../decide`, `POST .../ping`, `POST .../send-accounts`, `GET .../approval/pdf`.
   - **Submit** is allowed from `assigned`/`changes_requested` for the assignee **or a dispatcher/admin** (`caps.can_submit` matches). Empty managers body defaults to up to three `po_approve` managers.
6. **Follow up (ping)** — `POST /api/work-orders/{id}/approval/ping` (permission `edit`). Anyone on the slip (dispatcher, assignee, holder, coordinator; admin) nudges whoever holds the ball: submitted → selected manager(s); assigned/changes_requested → technician; approved → holder. Records a `ping` event, sends an in-app ping (kind `ping`) and an email (rides `email_notify_po`). Cooldown per record: `po_ping_cooldown_minutes` (default 30) → HTTP **429** `PingCooldown`. `sent_to_accounts` / `none` refuse with 400. Caps: `can_ping`, `ping_label`, `ping_targets`, `last_ping_at`, `ping_cooldown_minutes`.

Inbox API: `GET /api/po-approvals?q=` → lanes `incoming | assigned | changes | to_sign | ready | accounts`. Per-WO actions stay on `GET/POST /api/work-orders/{id}/approval*`. States: `none | assigned | submitted | changes_requested | approved | sent_to_accounts`. Extra grants: `po_dispatch`, `po_approve`, `accounts`.

**Email** (`backend/app/mailer.py`): admin Settings → Email. Provider `off` | `smtp` | `resend` — **preset is `resend`** (the app is set for the Resend API: admin pastes the `re_…` key + a From address on a domain verified in Resend; until then sends skip gracefully). `is_configured()` is honest: provider `resend` needs the API key, `smtp` needs a host — `email_ready` / `email_enabled` reflect that. Settings PUT validates mail only when an email value actually changes (a preset-but-unconfigured provider must not block unrelated saves). **No verified domain yet (Resend testing mode):** on Resend 403 `testing emails`/`verify a domain`, the app takes the **first email address in the rejection text** (Resend renders it as a markdown `[owner](mailto:owner)` link — do not require parentheses), saves it to `resend_test_inbox`, and retries from `onboarding@resend.dev` to the owner with subject `[TEST → <intended recipient>]` plus a note in text/HTML. **From address is optional for Resend**: `send_mail` only gates From for SMTP; with no From the app sends via the sandbox sender directly (to the saved inbox when known). Result carries `test_mode: true`, `to: owner`, `intended_to` (Settings test toast shows it). Sends self-heal once the domain is verified. Result carries `test_mode: true`, `to: owner`, `intended_to` (Settings test toast shows it). Sends self-heal once the domain is verified (normal send just succeeds). `resend_test_inbox` is a plain (non-secret) setting, editable in Settings → Email. From name/address, public URL for links, SMTP host/port/user/password/STARTTLS|SSL, or Resend API key. Secrets are write-only (`smtp_password_set` / `resend_api_key_set`). Blank password on save keeps the stored value. `POST /api/settings/email/test` sends a test.

- Verification: creating/changing a real email sends `/verify-email?token=`. Account can resend. `email_verified` on users. `@woms.local` seed addresses are never mailed.
- Password reset: Login **Forgot password?** → `/api/auth/forgot` (always 200) → `/reset-password?token=`.
- Requests: in-app inbox still writes. If mail is on, verified addresses also get PO / follow-up (`ping`) / Accounts / Assign-to / @mention emails (chat/follow off unless ticked; PO toggle also covers follow-ups). Pytest captures `mailer.OUTBOX` and does not hit the network.

**Logo:** `frontend/public/linkco-logo.png` — **transparent background**: white **Link** + red **co** + red molecule, for dark surfaces (sidebar dark mode, login brand panel, dark loading screen). `linkco-logo-dark.png` is the light-surface variant (ink **Link** via slate-900 `#0F172A` + red **co**/molecule); `BrandLogo.jsx` picks the variant from the theme. `favicon.png` is the red molecule, transparent. All three were recovered from the original black-backed PNG by unpremultiply-from-black, so edges stay smooth. Sidebar, login, loading, and browser tab use these only — no other logo files, and no `bg-black` patches (the black square is gone).

**Sites on create/edit:** camp sites plus F5 / Office / Accommodations — not SH5-only.

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
  reports.py                 Period briefings (`period_payload` / `period_pdf` / `period_xlsx`) + list exports
  security.py                JWT, roles, field-edit roles
  routers/                   auth, work_orders, dashboard, ops, catalog, collab, settings, …
frontend/src/
  pages/                     Dashboard, WorkOrders, WorkOrderDetail, Queue, Settings, Guide, …
  components/Tour.jsx        Deck-agnostic tour overlay (main + signing decks)
  components/SignSuccess.jsx "Signed & locked" stamp overlay after a manager signs
  components/MindMap3D.jsx   2D animated live mind map
  components/LoginScene.jsx  Three.js sign-in network
  lib/tour.js                TOUR_STEPS v1 + SIGNING_TOUR_STEPS v1
  lib/webgl.js               WebGL / reduced-motion helpers
  context/                   Auth, Ui (ask/toast), Tour, Theme
data/                        woms.db, app_config.json, attachments/  (gitignored except examples)
file.xlsx                    Live workbook at repo root — do not clobber in tests
tests/                       pytest
docs/EXCEL_ANALYSIS.md       Workbook inspection
docs/RECOVERY.md             Data loss / Docker / restore / admin commands
docs/PRODUCTION.md           Go-live checklist
docs/training/index.html     Operator training slides
scripts/recover.sh           Host file check + command cheat sheet
scripts/reset_admin.py       Reset or create admin login
SKILLS.md                    This file
```

Boot (`main._boot`): `init_db()`. If `wo_cache` is empty and Excel exists → `seed_from_excel(replace_lines=True)`. Else `excel_service.load()` from DB.

---

## 7. Save / Excel replica implementation

`ExcelService` (`backend/app/excel/service.py`):

- `get_all()` / `load()` → SQLite `wo_cache`.
- `update_record` / `update_records` / `create_record` / `delete_record` → **SQLite only**. `_excel_*` stay for import / reconcile / export.
- `create_record` assigns `{site_label}:DB-{hex}` and `_sheet` via `worksheet_labels`. Excel append at dump time does **not** change `record_id`.
- `export_database_to_excel()` dumps all DB rows into `file.xlsx` (lock + temp + validate + atomic replace). Match by `record_id` then `_row`+sheet; append unmatched creates; skip formula / due-date columns; never mass-delete Excel rows on a match miss.
- `archive_old_backups(days)` / `prune_archives(keep_days)`.
- `seed_from_excel` / `read_records_from` open with `read_only` then fall back, detect the header row in the first 8 rows, match data sheets by name or “MR log / Linkco”, and map up to 80 columns. Empty parse never calls `replace_wo_cache`. Seed refuses a workbook with &lt; 50% of live rows (`protect_live`).
- `replace_from_bytes` **parses a temp copy first**. Refuse non-xlsx / old `.xls` / 0 MR rows / &lt; 50% of live `wo_cache`. Only then backup, `_replace_excel_file`, and `seed_from_records` of the already-parsed rows. A misread upload must not wipe the database.

`resolve_excel_path`: if the configured path is not a file, substitute existing `ROOT/file.xlsx`. **Tests must not use `save_config(excel_path=missing.xlsx)` to simulate a missing workbook** — that still resolves to `file.xlsx` and can overwrite the real file. Stub `available()` instead. Always restore `file.xlsx` if a test hits it.

---

## 8. Backup / restore

Every `create_backup` writes **Excel + SQLite** and **must not fail the operator**:

- `{backup_dir}/{YYYY-MM-DD}/{stem}_{ts}_{reason}.xlsx` (durable copy: fsync + `_replace_excel_file` + size check, retries on lock/busy) and matching `.db` via `database.snapshot_to` (3 attempts + fsync).
- If the Excel copy fails, still snapshot SQLite and return the `.db` path. `create_backup` never raises to Backup now / autobackup.
- Midnight (`backup_time` default **00:00**) and Backup now: export DB → Excel first, then snapshot the pair. If Excel export fails, still snapshot SQLite and record the health error. Archive/prune errors must not abort the snapshot.
- Reasons: snapshots (`manual`, `auto`, `pre_restore`) and remaining Excel writes (`import`, `upload`, `reconcile`). Daily CRUD no longer creates write-safety copies.
- If Excel is missing, still snapshot SQLite (`woms_{ts}_{reason}.db`) and list that unpaired `.db`.
- Autobackup no longer skips when Excel is unavailable.
- Archive pairs older than 30 days under `backups/archive/YYYY-MM/`. Delete archives older than 180 days. That is the primary retention; `backup_ratio` is an optional extra cap.
- Download zips the pair. Upload accepts `.xlsx` / `.db` / zip of both.

### Restore

- Validate the backup workbook / `.db` before touching live files. Copy Excel via `_copy_file_durable` + `_replace_excel_file` (Docker EBUSY). Pre-restore snapshot is best-effort and must not block restore.
- If sibling `.db` exists (or the item is a `.db`): restore **database + Excel**.
- If Excel-only: replace `file.xlsx` only. **Do not silently seed/overwrite SQLite.** Operator must Seed from Excel if they want those rows.
- Settings UI: DB column, different confirm copy, `data-tour="backup"`.
- Health: backup row count (Excel and/or `wo_cache` in the `.db`) vs live DB count. Fail if backup has &lt; 50% of live rows.
- Prune (`backup_ratio`, default keep last 14 auto/manual): deletes paired `.db` with the `.xlsx`. Write-safety copies (`update`/`create`/`delete`/`bulk`/…) keep the last `backup_write_keep` (default 8).
- Autobackup default is **on**. Settings shows a warning if it is turned off.
- Folder picker (`GET/POST /api/settings/folders`) only lists/creates under the app root, `data/`, and the configured backup folder. Typed backup_dir may still be any writable non-system path.
- **Download** (`GET /api/settings/backups/download?path=`): zip of `.xlsx`+`.db` when paired, otherwise the single file.
- **Upload & restore**: `POST /api/settings/backups/upload` accepts `.xlsx` / `.xlsm` / `.db` / zip of both. Saves into the backup folder (does not replace live data by itself). UI then prompts Restore. Restore of a pair rolls SQLite + Excel; Excel-only does not seed the database.
- Operator commands: `docs/RECOVERY.md`, `scripts/recover.sh`, `scripts/reset_admin.py`. Docker down does **not** delete host `data/` or `backups/` (bind mounts).

Scheduler: `backend/app/backup.py`, 20s loop, `backup_auto_enabled`, `backup_time`, `backup_days` (0=Mon … 6=Sun), `backup_start_date`.

---

## 9. Auth, roles, pages

Permissions: `view`, `edit`, `create`, `delete`, `reports`, `analytics`, `settings`, `users`, `audit`, `backup`, `po_dispatch`, `po_approve`, `accounts`, plus page keys (`queue`, `materials`, …).

Default role grants (`config.permissions` / frontend `ROLE_PERMS`):

| Role | Can |
| ---- | --- |
| admin | everything |
| manager | view, edit, create, reports, analytics, audit, po_approve |
| user | view, edit, reports |
| readonly | view, reports, analytics |
| guest | view + explicitly granted pages |

`field_edit_roles` (default): `supplier` and `po_number` → admin, manager. Admin always can. Unlisted fields: anyone with `edit`.

User management (`/users`, permission `users`):

- Create / edit name-email-role-active / reset password / delete. Username 3–40 `[A-Za-z0-9._-]`. Cannot delete yourself. Cannot demote, disable, or delete the last active admin.
- Non-admin extra_permissions **union** with the role (grant `create`, `audit`, pages, …). **Cannot** extra-grant `users`, `settings`, or `backup` — those stay admin-only.
- `GET /api/users/access-catalog` lists grantable actions, `admin_only`, pages, role defaults. `GET /api/users/{id}` is one user.
- Account: `PUT /api/auth/profile` (name, email) and `POST /api/auth/password` (current + new, min 8). Password change returns a new `access_token` and bumps `token_version` so other sessions die. Logout revokes the current `jti`.
- Header search uses `GET /api/work-orders/suggest` (same as Ctrl/⌘+K). `POST /api/sync/upload` requires `settings` (admin seed). Header Upload control was removed; seed from Settings.
- `POST /api/sync/refresh` reloads SQLite (`hard: false`). It does **not** reseed from Excel.
- Frontend refetches `/api/auth/me` every 30s and on window focus so extra grants appear without a full re-login.

Status-change remarks (default): `*->ON HOLD`, `*->CLOSED`.

**Close order:** `POST /api/work-orders/{id}/close` with `{ remark, unit_price, price, total_price, final_price }`. Sets the first `closed_statuses` value (CLOSED), requires a remark when `status_change_remarks` includes `*->CLOSED`, fills `completion_date` if empty, and stores the four prices in SQLite. Header button on the MR page opens a price form.

PLACED requires `po_number` by default (`status_required_fields`).

---

## 10. Frontend

- React + Vite + Tailwind. Dev: `0.0.0.0:5173`, proxy `/api` → `127.0.0.1:8000`.
- UI look: light canvas, teal brand (`#0D9F8A`), white sidebar, compact KPI tiles with a left accent (UpKeep-style CMMS). Sidebar is **Daily / Lists / Ops / Admin** — Daily stays open (Queue, Work orders, Open, Overdue, Chat); other groups collapse. Work-order list defaults to a compact column set (`woms.columns`). Back and closing the tab prompt on unsaved MRs. Do not invent dashboard numbers to match a mock.
- **Mind map** (`MindMap3D.jsx`): Dashboard graph is **2D SVG** of **live** `/api/dashboard` counts — radial layout, always-on labels, flowing links, gentle node drift, root pulse. Rebuilds only when the graph **fingerprint** (id/value/label) changes so dashboard polling does not remount. Pause drift on hover. Skip motion when `prefers-reduced-motion`. Click a node still filters real records. List view remains as a toggle. Sign-in left panel still uses Three.js (`LoginScene.jsx`) — no fake KPIs.
- **Animations** (all skip when `prefers-reduced-motion`, CSS classes in `index.css`): login page staggers its entrance (`login-anim` / `brand-sweep`) and the sign-in button runs spinner → checkmark → navigate; the signature pad (`SignaturePad.jsx`) draws variable-width quadratic "ink" strokes, shows a looping self-drawing demo hint while empty, and a "Signature captured" tick on save; `SignSuccess.jsx` plays an ink flourish + "Signed & locked" stamp after an approving `decide` (on `/approvals` and the MR PO-approval panel).
- Production: `npm run build` → FastAPI serves `frontend/dist` when present.
- Confirmations: `UiContext.ask()` (restore, seed, reset, retry). Toasts for success/errors.
- Header: Search (completes WO / supplier / item / person / camp site), command palette (`Ctrl/⌘+K`), Refresh, Live|Offline. `?` opens `/guide` unless a tour is active.
- **Notification popups** (`NotifyPopups.jsx`, top-right, z-85): the 8s inbox poll in Layout diffs items against `localStorage["woms.notify.last.<user>"]` (baseline flag `woms.notify.baseline.<user>` so the first load never replays) and pops new ones — managers get a branded “Document to sign” card for `po` kind with a **Review & sign** action that deep-links to `/approvals?id=…` and marks the notification read. Auto-dismiss 15s, max 4 stacked.
- Work-order list columns persist in `localStorage["woms.columns"]`. The Site column shows the camp (`Site - 1`, `L1`, …) when it can be inferred from WO Asset Name; `department` in SQLite stays the worksheet (`SH5-SH1` / `F5`). Work Orders site chips and the Site dropdown use `filter_site_items` (same camps as Dashboard). The Dashboard mind map **Sites** branch and Site performance table use those same camp/sheet chips (`group_by_sites`). Search applies the filters currently set.
- Reports (`/reports`): Daily and Weekly are on-screen briefings. Choose a calendar date (prev/next, Today / This week). Daily = that day only; weekly = ISO Monday–Sunday of that date. JSON at `GET /api/reports/{daily|weekly}?fmt=json&as_of=`. PDF is one A4 portrait page; XLSX is one sheet with `fitToHeight=1`. Other report kinds stay download-only under the More tab.
- Work order editor: **one** Items & suppliers form. Type to complete supplier and item names (`TypeAhead`). Alt+Enter adds a row. No “Add supplier” on the MR page — add vendors on Materials (Catalog tab can **remove** them; `DELETE /api/catalog/suppliers/{id}`). Supplier list is unique (`unique_supplier_names`). Type `@` in remarks/chat. Header search hits `GET /api/work-orders/suggest`. List search also matches `mr_lines`. Presence heartbeat shows who else has the MR open.
- **Chat:** `GET /api/work-orders/{id}/chat` does **not** create a thread. `POST` the first message does. Listing threads hides empty DMs and empty WO threads. UI: People click opens a draft until Send. **Clear chat** (`DELETE /api/chat/threads/{id}/messages`) and **Delete chat** (`DELETE /api/chat/threads/{id}`; General is protected). Author or admin can delete one message. Header ping/inbox polls every 8s (not 3s).
- Filters start collapsed; chips remove filters. A **Search** button applies the current filters (Dashboard opens the matching Work Orders list).
- Settings Excel upload / Upload & restore show a progress overlay (Uploading Excel → Applying backup → Applied). Work runs in a background job (`POST /api/settings/jobs/excel-upload` or `/jobs/backup-apply`, poll `GET /api/settings/jobs/{id}`) so login stays available. A request timeout must **not** clear the JWT.
- After Settings StrReplace, **assert `function DatabasePanel` still exists** if you insert `<DatabasePanel />` (vite can build while runtime ReferenceError).

### Tour / Guide

- Main tour: `TOUR_VERSION = "v1"`. Key: `localStorage["woms.tour.v1:"+username] = "done"`.
- **Do not bump `TOUR_VERSION`** just to add a step. Replay from Guide / Account / header help shows new steps.
- First-run auto-start (~800ms) re-checks `tourSeen` so Skip does not restart.
- `measureTarget` must pick a **visible** `[data-tour]` (desktop vs mobile sidebar).
- Overlay click does **not** skip. Esc skips.
- Current main-tour `data-tour` ids: `nav-work`, `search`, `live`, `dashboard`, `wo-list`, `filters`, `wo-new`, `wo-tabs`, `wo-save`, `queue`, `backup`, `command`, `shortcuts`, `presence`.
- Admin backup step: `need: "backup"`, `page: "settings"`, target `backup`. Title/body must say every backup pairs Excel + SQLite (saves, Backup now, schedule) — not “snapshots, not every save”.

**Manager signing tour** (separate deck, `SIGNING_TOUR_VERSION = "v1"`):

- Steps in `SIGNING_TOUR_STEPS` (same file `lib/tour.js`). Storage: `localStorage["woms.signingTour.v1:"+username] = "done"`.
- Deck choice lives in `TourContext` (`deck` = `main` | `signing`; `start()` = main, `startSigning()` = signing, `startDeck(name)` generic). `Tour.jsx` is deck-agnostic — it renders `steps` from context and navigates to each step's `path` (`/approvals`).
- Auto-starts **once** on the user's first visit to `/approvals` when the filtered steps are non-empty (`po_approve` / `po_dispatch` / `accounts` grants; frontend `can()` already treats admin as all-perms). Replay via Guide (manager card) or the **How signing works** button on `/approvals` and the MR PO-approval panel.
- `/approvals` UI (rebuilt): workflow stepper (Request → Technician → Managers → Signed → Accounts) with a plain-language status caption; a **Next step** card that shows only the actions currently available; **Review & sign…** opens `SignWindow.jsx` — a two-step modal (1 · View the request = summary + PDF, 2 · Sign the request = draw, pick the recipient, Sign & send with a lock confirm, or Return with changes). The signing tour auto-opens the window at step 2 when it reaches the hands-on steps. MR-page `PoApproval.jsx` reuses the same window.
- Signing-desk `data-tour` ids (on `PoApprovals.jsx` / `SignaturePad.jsx`): `appr-head`, `appr-steps`, `appr-lanes`, `appr-list`, `appr-pdf`, `sign-pad` (signature canvas), `sign-return-to`, `sign-send`, `sign-return`, `appr-followup` (follow-up panel), `appr-accounts`.
- Do not bump `SIGNING_TOUR_VERSION` when adding steps either; replay shows them.

---

## 11. API map (prefixes)

| Prefix | Purpose |
| ------ | ------- |
| `/api/health` | Liveness + record count |
| `/api/auth` | login, me, logout, password, profile, layout, forgot, reset-password, verify-email, verify-email/resend |
| `/api/po-approvals` | Role inbox for the PO signatures desk (`lanes`, `counts`, `default_lane`) |
| `/api/work-orders` | list, suggest, CRUD, bulk, claim, close, watch, presence, chat, timeline, seen, PDF sheet, PO approval (`/{id}/approval` get/assign/submit/decide/send-accounts/**ping** + `/approval/pdf`) |
| `/api/dashboard` | KPIs / charts from live records |
| `/api/ops` | queue, digest, alerts, handover, health scan |
| `/api/catalog` | suppliers, materials, aliases, MR lines |
| `/api/collab` | chat (incl. clear/delete thread/message), projects, notifications, saved views |
| `/api/files` | attachments |
| `/api/reports` | Period briefings + Excel/CSV/PDF. `render()` supports **every** kind: daily/weekly → period briefing; monthly/yearly/open/overdue/closed/delay/department/technician → record-list exports via `records_for_report` + `to_pdf/to_xlsx/to_csv` (previously returned None — all those downloads were broken). Weekly PDF/XLSX embed a New/Closed/Overdue bar chart (reportlab Drawing / openpyxl BarChart); delay report filters delayed/blockade/issue-flagged records. `GET /{kind}` kinds: `daily`, `weekly`, `monthly`, `yearly`, `open`, `overdue`, `closed`, `delay`, `department`, `technician`. `fmt=pdf\|xlsx\|csv\|json`. Daily/weekly take `as_of` or `date` (ISO day). JSON for daily/weekly is `period_payload`. PDF for those kinds is inline, one page. |
| `/api/audit` | field-level audit log |
| `/api/users` | list, access-catalog, CRUD, extra grants |
| `/api/settings` | config, mapping scan, backups, database seed/reset/upload, `POST /jobs/excel-upload`, `POST /jobs/backup-apply`, `GET /jobs/{id}`, `POST /email/test` |
| `/api/sync` | ping, refresh (`hard: false` reloads DB), upload (settings / seed) |

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
| `tests/test_backup_bulletproof.py` | Backup still snapshots SQLite if Excel copy fails; upload refuses garbage/empty/tiny workbooks; header-row and sheet-name read |
| `tests/test_excel_and_api.py` | Read Excel, DB-only create + export, backup schedule/archive/prune, close order |
| `tests/test_ops_pack.py` | Queue, digest, timeline, mapping, backup health. Claim uses a technician (`arun`), not admin |
| `tests/test_collab_*.py` | Chat, watches, row restore |
| `tests/test_materials_catalog.py` | Lines, aliases, unique supplier dropdown, paired create-backup, line search, suggest, presence |
| `tests/test_delay_sites.py` | Extra sites / delay rules / camp filters / mind-map Sites camps |
| `tests/test_reports.py` | Daily/weekly window, one-page PDF, one-sheet XLSX, JSON API |
| `tests/test_production_hardening.py` | Login lockout, jwt_secret stripped from Settings, password min 8, `/api/health` SQLite + request id |
| `tests/test_users_access.py` | User CRUD, extra grants, profile, password, last-admin guard |
| `tests/test_audit_fixes.py` | Logout revoke, password invalidates token, upload needs settings, folder jail, write-backup prune |
| `tests/test_priority_blockades.py` | Priority case-fold, blockades exclude OPEN/PLACED, flag=blockade |
| `tests/test_business_flow.py` | Dummy multi-line MR, delete WO, mentions, chat clear/delete, supplier add/remove, backup pair |
| `tests/test_po_approval.py` | Technician-only assign, empty-type due date, PLACED overdue via ETA, PO assign → submit → sign → lock → Accounts, inbox lanes, manager must wait for resubmit |
| `tests/test_po_followup.py` | Follow-up ping targets per state, cooldown 429, permission refusals, caps, follow-up email via OUTBOX |
| `tests/test_po_approval.py` (added) | Regression: `/approval/unassign` route works (403 for outsiders), `/approval/submit` honors `{managers}`, admin/dispatcher `can_submit` |
| `tests/test_email.py` | Settings hide SMTP/Resend secrets and keep blank-password, verification + reset links, request email to verified addresses, skip `@woms.local` | + Resend no-domain testing-mode redirect (learn owner, `[TEST → …]` resend)

Pitfalls (do not repeat):

- `save_config(excel_path=missing.xlsx)` does **not** make Excel unavailable (`resolve_excel_path` falls back to `file.xlsx`). Stub `available()`. Do not `get_all(force=True)` after a DB-only create.
- Do not leave `file.xlsx` modified. Workbook fixtures copy to `tmp_path` and restore config `excel_path` / `backup_dir`.
- `text.replace("    def create_record(\n"` misses one-line defs.
- Sequential StrReplace on a stale `database.py` snapshot fails; re-read the file.
- Tests share `data/woms.db`. Prefer fixture seed (`get_all(force=True)`) over assuming empty.

---

## 13. Git / GitHub

- Session branch only: `arena/01a0863b-excel-dashboard`. Do not switch, rename, or push other branches.
- Push: `git push origin arena/01a0863b-excel-dashboard`. Never force-push.
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
3. Write SQLite only for daily CRUD. Excel dump is midnight / Backup now.
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

1. Midnight and Backup now export DB → Excel then pair `.xlsx` + `.db`. Archive after 30 days; prune archives after 180. Excel copy failure must still snapshot SQLite; `create_backup` never raises.
2. Restore: validate sources; pair → both; Excel-only leftover files → Excel only, no silent seed. Use inode-safe replace.
3. Download zips the pair. Upload accepts `.xlsx` / `.db` / zip into the backup folder, then the UI prompts Restore.
4. Settings Excel upload parses the temp workbook **before** replacing live Excel / seeding. Refuse 0-row or &lt; 50% of live.
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
- [x] Manager signing tour on the Purchase Approval desk (auto once + replay)
- [x] Default users recreated after reset
- [x] Download / upload / restore snapshots (xlsx, db, zip)
- [x] Recovery commands (`docs/RECOVERY.md`)
- [x] Multiple materials × suppliers per MR (`mr_lines`; item 1 / supplier 1)
- [x] Daily / weekly reports from a chosen date (that day or that ISO week only; one-page PDF)
- [x] One MR supplier form (dropdown only); unique supplier names; @mentions; search suggestions; backups always pair Excel + DB
- [x] Typeahead search + command palette + shortcuts; list search matches line items; live presence on an open MR
- [x] Production hardening (login lockout, no jwt_secret in API, attachment path check, password min 8) + operator training slides
- [x] User management: create / modify / delete, access grants, Account profile + password
- [x] Audit fixes: header suggest search, admin-only workbook seed, default-password gate, JWT logout revoke, extra-grant limits, write-backup prune, autobackup on by default
- [x] Camp sites: SH5 Site - 1/2/3/4A/5/7 and SH1 L1, L2, L3, L4, L5, L7, LS1, LS2 (filters + create), no new Excel sheets
- [x] Chat: Clear / Delete buttons; no conversation until the user sends; delete own message; catalog add/remove suppliers
- [x] Ops-desk polish: Daily nav, compact list columns, unsaved-change guard, abort in-flight list fetches
- [x] Linkco logo + favicon (local PNG)
- [x] Assign to = technicians (`role=user`) only; keep current name if already assigned
- [x] All sites on WO create/edit (camps + F5/Office/Accommodations)
- [x] Empty purchase type → operator picks due date (date only); skip 14-day default
- [x] Close order captures unit / price / total / final in SQLite (not Excel)
- [x] PO digital signature: dispatcher assigns tech → PDF to manager → sign or return → lock → Accounts
- [x] PO follow-up: ping whoever holds the ball (manager / technician / holder) in-app + email, cooldown-protected
- [x] Email preset for the Resend API (change-only validation; honest `is_configured`)
- [x] Email: admin SMTP or Resend; verification + password-reset links; PO/assign/mention requests to verified addresses
- [x] Overdue: OPEN/PENDING = due date; PLACED = ETA (`closed_date`); `is_delayed` unchanged

When you complete or change a requirement, tick/retarget it here.

---

## 16. Decision log (append, do not rewrite history)

AI: add a bullet when you make a lasting decision. Date + short why.

- **2026-09 (aef7883)** Excel is no longer SoT. User reversed earlier Excel-SoT. DB first, Excel copy on save. Excel failure keeps DB.
- **2026-09** Admin reset wipes **everything** (users, chat, settings, WOs), then new DB + seed. Recreate default logins. Keep `app_config.json`.
- **2026-09 (dc7bc07)** Snapshots (`manual`/`auto`/`pre_restore`) pair `.xlsx`+`.db`. Excel-only restore of leftover files does not seed DB.
- **2026-09 (feb7b71)** Tour v1; replay instead of bumping version when adding steps. Overlay click does not skip.
- **2026-09** `X-Frame-Options: SAMEORIGIN` required for preview. Do not set `DENY`.
- **2026-09** Pydantic ≥ 2.12 for Python 3.14; do not pin 2.9.x.
- **2026-09** Backup UI: Download (zip pair), Upload & restore (.xlsx/.db/zip). Recovery commands in `docs/RECOVERY.md`.
- **2026-09-08 (a18f4e3)** Typeahead search, Ctrl/⌘+K, list j/k/Enter/x, presence, WAL. Tour step `keys`. `GET /suggest` must stay before `/{wo_id}`.
- **2026-09-08** Tour backup step no longer says “snapshots, not every save”. Every `create_backup` reason pairs `.xlsx`+`.db`.
- **2026-09-08** Production audit: lockout, hide jwt_secret, attachment path, generic 500s, password min 8. Training deck `docs/training/index.html`. Go-live still requires password change, HTTPS off-LAN, autobackup on, off-box copies.
- **2026-09-08** Users page is full CRUD + access matrix. Extra permissions union with role. Last admin cannot be removed. Account can edit name/email and password.
- **2026-09-08** Audit follow-up: header search uses `/suggest`; `/api/sync/upload` is settings-only; default passwords must be changed (`must_change_password`, skipped under pytest); logout revokes JWT `jti`; extras cannot grant users/settings/backup; write-safety backups prune to 8; autobackup defaults on; refresh `hard: false`.
- **2026-09-08** Live `file.xlsx` replaced from `1. Material Request_LOG - Test 002.xlsx` via `replace_from_bytes` (paired backup, then seed). `wo_cache` replaced 2182 → 2193 by `record_id`. Do not append a second copy of the log. Several MRs per IM WO stay — that is not a duplicate row.
- **2026-09-08** Work Orders `/options.sites` is `filter_site_items` (camp chips + Site dropdown). Suggest search includes sites. Excel replace falls back to copy-into-inode when Docker bind-mount `os.replace` returns EBUSY.
- **2026-09-08** Dashboard mind map Sites branch (and Site performance table) group by camp / sheet chips (`SH5-S3`, `L1`, `F5`, …), not only the Excel worksheet. Click still filters `department`.
- **2026-09-08** Excel upload/seed and backup apply run off the event loop (thread + job). UI shows upload bar, applying-backup bar, then an applied notification. `/api/auth/me` timeout must not log the user out.
- **2026-09-08** Three.js mind map (live counts, click → Open list) plus a decorative login network. No invented statistics. Reduced-motion / no-WebGL falls back to the 2D tree.
- **2026-09-09** User reversed per-save Excel. SQLite is the only live store. Midnight (default 00:00) exports all DB rows into `file.xlsx` and snapshots SQLite. Archive pairs after 30 days; delete archives after 180. Close order button. 3D mind map fingerprints the graph so dashboard polls do not remount WebGL; sprite labels + min-height.
- **2026-09-09** Seed technician logins Abubacar, Arun, Nesar, Yousuf (`TEAM_USERS`). Assign-to save/bulk/create pings that user in the inbox when the name matches username or full_name.
- **2026-09-09** Mind map is 2D SVG with animation (not WebGL orbit). Labels stay readable; motion pauses on hover / reduced-motion.
- **2026-09-09** Backup must not fail: durable Excel copy with retry/fsync, SQLite snapshot retries, still snapshot `.db` if Excel copy fails. Excel upload reads the temp workbook (header-row scan, fuzzy sheet names) before replacing live files; refuse empty / &lt; 50% so `wo_cache` is not wiped.
- **2026-09-09** PO signatures live on `/approvals` (not only the MR tab). `GET /api/po-approvals` is the role inbox. Manager `decide()` only from `submitted`.
- **2026-09-09** Email is optional. Admin picks SMTP or Resend. Verification and reset go through email; PO/request pings also email verified addresses. Inbox stays in-app.
- **2026-09-09 (this session)** Logo made transparent: black background removed from `linkco-logo.png`/`favicon.png` (unpremultiply-from-black keeps antialiased edges), new light-surface variant `linkco-logo-dark.png` (ink Link), `BrandLogo.jsx` switches variants by theme, `bg-black` patches dropped.
## Production deployment (added 2026-09-10)

**Topology:** browser -> nginx :8000 (public) -> uvicorn 127.0.0.1:8001 (loopback, never exposed). nginx serves `frontend/dist` with immutable caching for hashed `/assets` (pre-compressed via `deploy/precompress.sh` + `gzip_static`), `no-cache` index.html, SPA fallback, `client_max_body_size 25m`, 300s proxy read timeout (big reports), login rate-limit 20 r/m burst 10 (429), JSON 502 page (`deploy/maintenance.json`), `server_tokens off`. Logs: `data/logs/nginx-{access,error}.log`, `backend.log`.

**Commands:** start/stop = `deploy/start_production.sh [stop]`; config test = `deploy/nginx/sbin/nginx -t -c deploy/nginx.conf`; frontend rebuild requires `deploy/precompress.sh` afterwards (start script does it). nginx 1.28.3 was built from source (GitHub mirror; apt mirrors are blocked in this sandbox) into `deploy/nginx/` which is **git-ignored** — rebuild steps in deploy/README.md. The config ships `deploy/mime.types` next to it so it is self-contained; note `return`/rewrite directives are unavailable in this build (no PCRE) — use `try_files` + static error pages instead.

**Backend changes that go with it:** `run.py` binds `WOMS_HOST` (default 127.0.0.1) / `WOMS_PORT` (default 8001) and trusts X-Forwarded-* only from 127.0.0.1; `app/main.py` CORS defaults to same-origin only (`WOMS_CORS_ORIGINS` env to open, "*" for all). Vite dev proxy target follows `WOMS_PORT` (default 8001).

**Docker (added 2026-09-10):** `docker-run.bat` (Windows) / `docker-run.sh` (Linux/macOS) → `docker compose up --build` → one image, production topology inside: nginx installed from Debian packages, `deploy/nginx-docker.conf` (container paths, logs to /app/data/logs host mount), `deploy/docker-entrypoint.sh` starts uvicorn loopback 8001 then `exec nginx -g 'daemon off;'`. Frontend built + pre-gzipped in the node stage (`gzip_static` served). Mounts: `./file.xlsx`, `./data/`, `./backups/` — the image is stateless. HEALTHCHECK hits nginx :8000. `WOMS_JWT_SECRET` / `WOMS_CORS_ORIGINS` env passthrough in compose. Local dev (run.bat/run.sh --local/scripts/start-api.bat) = uvicorn 127.0.0.1:8001 + Vite 5173 as the entry (proxies /api). NEVER bind uvicorn 0.0.0.0 outside the container image.

**Pitfall:** the sandbox snapshot keeps restoring a STALE `file.xlsx` (3.29 MB live-DB copy) over the pristine committed one (4,033,425 B). Symptom: `test_reconcile_migrates_sqlite_delay_into_new_columns` fails with `wrote_excel False` (delay columns already exist in the stale copy). Fix: `git checkout -- file.xlsx` (with servers down), then re-run. Always `git status --short file.xlsx` before committing.

- **2026-09-10 (MR + Accounts toggle)** User round: (1) "IM WO" renamed to "MR" in ALL display labels (tables, PDFs, forms, tour, Guide) - EXCEPTION: the Excel column mapping name "IM WO Completion" (config.completion_date, WorkOrderDetail field def) must match the real workbook header and is untouched. (2) `po_accounts_process` config flag (default False) gates the Accounts step: inbox hides the accounts lane (data kept), `capabilities.can_send_accounts` false, `send_accounts()` raises with guidance, default_lane skips it; admin toggle in Settings > Purchase approval process re-enables (legacy sent_to_accounts rows reappear). Tests that exercise the legacy Accounts flow monkeypatch `approvals.accounts_enabled`. (3) Emails intentionally kept: submit -> managers ("po"), decide sign -> holder+tech, decide return -> technician; only the Accounts filing email hides with the step.
- **2026-09-10 (Gmail)** `email_provider` now accepts `gmail` (alias `google`). mailer resolves Gmail to the preset smtp.gmail.com:587 STARTTLS with login = the Gmail address (smtp_username, falls back to email_from_address) and requires a 16-character Google App password (regular passwords rejected; spaces stripped before login). Settings PUT fills the preset and 422s with guidance when the App password is missing. Resend and custom SMTP unchanged.
- **2026-09-10 (desk rebuild)** User feedback round: (1) `/approval/route` POST 405'd — frontend called it but the router endpoint never existed (unmatched /api POSTs fall through to the GET-only SPA mount and return 405, remember this when debugging "Method Not Allowed"); endpoint added. (2) `decide` router dropped `return_to` — the recipient dropdown was ignored; now passed. (3) `send-accounts` accepts optional `to`. (4) Sign window closes itself after Sign & send and plays the SignSuccess stamp (setCelebrate was never called — dead code). (5) Personal inbox views shipped: `inbox()` now returns `mine` = {to_sign, sent, signed} + mine_counts, computed independent of lane visibility; desk lanes gated to can_dispatch/can_accounts in the UI. (6) Remind = per-row ping with custom message (reuses /approval/ping, cooldown-aware). (7) Buttons: `.btn-go` emerald (approve/send), `.btn-warn` amber (remind/return-with-changes), `.btn-danger` rose (unassign).
- **2026-09-10** PO PDF signature embed was silently broken under reportlab 5.x (ImageReader rejection + "80mm" string width) — signed slips printed no signature. Fixed both, regression test asserts the image XObject exists only on signed PDFs.
- **2026-09-10** Audit fixes: `render()` now handles every report kind (list exports were all None → downloads 500/broken); delay report filters delayed+blockade+issue; Resend owner parse handles markdown mailto links and From is optional for Resend; notification popups in-app; Settings Email has its own Save button.
- **2026-09-09 (this session)** Approvals desk UX rebuild + fixes: registered the missing `POST /{id}/approval/unassign` route (405 reported in the field), submit now passes the picked managers through (`SubmitPoBody`) and dispatchers/admins can submit (`can_submit`), desk shows a five-stage stepper with status captions and a Next-step card, and signing moved into a two-step `SignWindow` modal (view the request → sign/return) shared with the MR approval panel; signing tour auto-opens the window on hands-on steps.

- **2026-09-09 (this session)** Resend testing mode: unverified-domain 403s no longer fail — mailer learns the owner inbox from the error, persists `resend_test_inbox`, and delivers from onboarding@resend.dev to the owner with [TEST -> recipient] labels; self-heals after domain verification.

- **2026-09-09 (this session)** PO follow-up: `POST /{id}/approval/ping` pings the pending person per state with a `ping` history event, in-app inbox ping, and email riding `email_notify_po`; cooldown `po_ping_cooldown_minutes` (30) returns 429. Mail is preset to `resend` (key + verified-domain From to activate); `is_configured` now requires the provider secret; Settings PUT validates mail only when email values change so unfinished email setup never blocks backup/other saves.

- **2026-09-09 (this session)** Motion + onboarding pass: login entrance animation and spinner→checkmark sign-in button; signature pad gets ink-weight strokes, self-drawing demo hint, "captured" tick; `SignSuccess` stamp overlay after an approving decide; dedicated manager signing tour (`SIGNING_TOUR_STEPS v1`, separate storage key, auto-starts once on first `/approvals` visit for people who can sign; replay from Guide / "How signing works"). `TourContext` now hosts two decks (`main`, `signing`); `Tour.jsx` is deck-agnostic. Training deck gained a "What's new — September 2026" section and its save/backup slides were corrected to DB-first (saves write SQLite only; Excel updates at midnight / Backup now). All new motion respects `prefers-reduced-motion`.
