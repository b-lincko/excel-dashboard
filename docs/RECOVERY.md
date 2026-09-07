# Recovery and help commands

Live history is **`data/woms.db`**. Excel **`file.xlsx`** is a replica. Docker bind-mounts `./data`, `./backups`, and `./file.xlsx` from the **host** folder — if the container is down, the database is still on disk.

Full command list for data loss, Docker down, restore, users, and admin password.

Run commands from the project root unless noted.

```bash
cd /path/to/excel-dashboard
```

On Windows PowerShell, use the same paths with `\` or run Git Bash.

---

## 1. Where is the data?

| What | Host path | Inside Docker |
| ---- | --------- | ------------- |
| Live database | `data/woms.db` | `/app/data/woms.db` |
| Column mapping / settings | `data/app_config.json` | `/app/data/app_config.json` |
| JWT secret | `data/.jwt_secret` | `/app/data/.jwt_secret` |
| Attachments | `data/attachments/` | `/app/data/attachments/` |
| Excel replica | `file.xlsx` | `/app/file.xlsx` |
| Snapshots | `backups/YYYY-MM-DD/*.xlsx` + `*.db` | `/app/backups/...` |

```bash
# Find the database on the host
ls -lh data/woms.db file.xlsx backups
find . -name 'woms.db' -o -name 'file.xlsx' | head

# If you are not sure which folder Docker used
docker inspect linkco-mr --format '{{json .Mounts}}'
```

SQLite extras (safe to copy together): `data/woms.db-wal`, `data/woms.db-shm`.

---

## 2. Docker is down / will not start

```bash
# Status
docker info
docker ps -a --filter name=linkco-mr
docker compose -f docker-compose.yml ps

# Start the engine (Linux)
sudo systemctl start docker
sudo systemctl enable --now docker

# Rebuild and start (keeps host data/ and backups/)
./docker-run.sh
# or
docker compose -f docker-compose.yml up --build -d

# Logs
docker logs linkco-mr --tail 200
docker compose -f docker-compose.yml logs --tail 200

# Health
curl -fsS http://127.0.0.1:8000/api/health

# Stop / remove container only (does NOT delete host data/)
docker compose -f docker-compose.yml down
```

If Docker itself is broken, run without it:

```bash
./run.sh --local
```

API: http://127.0.0.1:8000 · UI: http://127.0.0.1:5173

Default logins: `admin` / `admin123` · `manager` / `manager123` · `user` / `user123`

---

## 3. Copy data off a dead container

Host bind mounts mean `data/woms.db` is already on the host. If you ever ran without mounts:

```bash
mkdir -p recover
docker cp linkco-mr:/app/data/woms.db recover/woms.db
docker cp linkco-mr:/app/file.xlsx recover/file.xlsx
docker cp linkco-mr:/app/data/app_config.json recover/app_config.json
docker cp linkco-mr:/app/backups recover/backups
```

Copy recovered files back:

```bash
cp recover/woms.db data/woms.db
cp recover/file.xlsx file.xlsx
cp recover/app_config.json data/app_config.json
```

Then start the app. Do **not** delete `app_config.json` (column mapping).

---

## 4. Restore a snapshot (Excel + database)

### In the app (preferred)

Settings → Backup system (admin / backup permission):

1. **Backup now** — writes a paired `.xlsx` + `.db`
2. **Download** — zip of the pair (or Excel only)
3. **Upload & restore** — `.xlsx`, `.xlsm`, `.db`, or a zip of both, then confirm Restore
4. **Restore** on a row — paired snapshot rolls back SQLite + Excel; Excel-only does not overwrite live history

### From the host (app stopped)

Pick a snapshot under `backups/YYYY-MM-DD/`:

```bash
SNAP=backups/2026-09-07/file_2026-09-07_020000_manual   # no extension

# 1. Stop the app so SQLite is not open
docker compose -f docker-compose.yml down
# or Ctrl+C on ./run.sh

# 2. Keep a copy of whatever is live now
mkdir -p recover/pre-restore
cp -a data/woms.db recover/pre-restore/ 2>/dev/null || true
cp -a file.xlsx recover/pre-restore/ 2>/dev/null || true

# 3. Restore Excel replica
cp "${SNAP}.xlsx" file.xlsx

# 4. Restore live database (only if the .db pair exists)
cp "${SNAP}.db" data/woms.db
rm -f data/woms.db-wal data/woms.db-shm

# 5. Start
./docker-run.sh
```

Excel-only file (reason `update` / `create` / …) replaces `file.xlsx` only. To load those rows into SQLite afterwards: Settings → **Seed from Excel**.

### From a downloaded zip on another PC

```bash
unzip file_2026-09-07_020000_manual.zip -d /tmp/woms-snap
# copy the .xlsx and .db as above, then start the app
```

Or: start the app → Settings → Upload & restore → choose the zip.

---

## 5. Database missing or empty

```bash
ls -lh data/woms.db file.xlsx

# Boot seeds from Excel if wo_cache is empty. Restart:
docker compose -f docker-compose.yml restart
# or
./run.sh --local
```

If the DB file is gone but Excel exists: start the app, sign in as admin, Settings → **Seed from Excel**.

If both are gone: restore from `backups/` (section 4) or re-upload `file.xlsx` via Settings → **Upload Excel then seed**.

Check row count without the UI:

```bash
sqlite3 data/woms.db "SELECT COUNT(*) FROM wo_cache; SELECT username, role FROM users;"
```

Docker:

```bash
docker compose exec woms python -c "from app import database; print(database.wo_cache_count(), [u['username'] for u in database.list_users()])"
```

---

## 6. Change database / Excel / backup settings

In the app: **Settings** → Excel path, backup folder, autobackup, column mapping → **Save configuration**.

On disk (`data/app_config.json` — keep this file):

```bash
# Backup mapping before editing
cp data/app_config.json data/app_config.json.bak

# Useful keys: excel_path, backup_dir, backup_auto_enabled, mapping, jwt_secret
python3 - <<'PY'
import json
from pathlib import Path
p = Path("data/app_config.json")
cfg = json.loads(p.read_text())
print("excel_path:", cfg.get("excel_path"))
print("backup_dir:", cfg.get("backup_dir"))
print("backup_auto_enabled:", cfg.get("backup_auto_enabled"))
PY
```

After editing JSON, restart the API. Do not point `excel_path` at a missing file if `file.xlsx` still exists in the project root — the app will fall back to `file.xlsx`.

---

## 7. Users — add, disable, change admin

### In the app

**Users** page (admin): create user, set role (`admin` / `manager` / `user` / `readonly` / `guest`), reset password, deactivate.

### Reset admin password from the host (app may be stopped)

```bash
python3 scripts/reset_admin.py
# optional
python3 scripts/reset_admin.py --username admin --password 'admin123'
```

### SQL (only if Python script is unavailable)

```bash
# Recreate default admin by deleting users then letting init_db run — last resort.
# Prefer scripts/reset_admin.py which hashes the password correctly.
```

### Add a user from Python

```bash
cd backend
python3 - <<'PY'
from app import database
database.init_db()
database.create_user("sam", "Sam", "sam@local", "ChangeMe1", "manager")
print([u["username"] for u in database.list_users()])
PY
```

### Promote someone to admin

```bash
cd backend
python3 - <<'PY'
from app import database
database.init_db()
u = database.get_user_by_username("sam")
database.update_user(u["id"], role="admin", is_active=1)
print("now admin:", u["username"])
PY
```

After a full **Reset database** in Settings (type `DELETE`): default logins come back (`admin` / `admin123`). Mapping in `app_config.json` is kept.

---

## 8. Data-loss checklist

1. Stop writing. Stop the app if you can.
2. Copy `data/`, `file.xlsx`, and `backups/` to another disk.
3. List snapshots: `ls -lt backups/* | head`
4. Restore the newest **paired** `*_manual.db` / `*_auto.db` (section 4).
5. Start the app. Confirm `/api/health` and a known work order.
6. If only Excel survived: Seed from Excel (users stay) or Upload Excel then seed.
7. If logins are lost: `python3 scripts/reset_admin.py` then sign in as admin.

Never replace `data/woms.db` while the API is running. Never delete `app_config.json` unless you intend to lose column mapping.

---

## 9. One-liners

```bash
# Health
curl -s http://127.0.0.1:8000/api/health

# Host files
ls -lh data/woms.db file.xlsx
ls -lt backups/*/*.db backups/*/*.xlsx 2>/dev/null | head

# Docker
docker compose -f docker-compose.yml up --build -d
docker logs linkco-mr --tail 100
docker compose -f docker-compose.yml down

# Local without Docker
./run.sh --local

# Admin password
python3 scripts/reset_admin.py --password 'admin123'

# Count MRs
sqlite3 data/woms.db 'SELECT COUNT(*) FROM wo_cache;'
```
