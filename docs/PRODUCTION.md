# Production go-live checklist

The app is a working operations desk, not a mock. Use this list before people depend on it.

## Ready in the product

- Database is the only live MR history; Excel is a midnight replica plus Backup now.
- Conflict warning (HTTP 409) instead of silent overwrite.
- Excel write: lock → paired backup → temp → validate → atomic replace.
- Excel failure keeps the database row.
- Paired backups (`.xlsx` + `.db`) on every save, Backup now, and the schedule.
- Restore of a pair rolls both back; Excel-only leftover files do not seed SQLite.
- Roles and permissions; audit log; JWT sessions (12 hours).
- Login lockout after 8 failed attempts / 10 minutes (per username + IP).
- JWT secret is never returned from Settings.
- Attachment download stays inside `data/attachments/`.
- Unhandled API errors return `Internal server error` unless `WOMS_DEBUG=1`.
- New user passwords must be at least 8 characters.
- Docker health check on `/api/health`. Bind mounts keep `data/`, `backups/`, `file.xlsx` on the host.

## Must do on the live machine

1. **Change every default password** (`admin/admin123`, `manager/manager123`, `user/user123`). Create named accounts. Disable unused defaults.
2. **Do not expose the app on the public internet without HTTPS.** Put nginx/Caddy or IIS in front with TLS. The API itself is HTTP.
3. Set `WOMS_JWT_SECRET` in the environment (or keep `data/.jwt_secret` with mode 600). Do not commit it.
4. Confirm **Autobackup** is on in Settings (default on for new configs). Confirm a paired file appears under `backups/YYYY-MM-DD/`. Per-save copies keep the last 8.
5. Copy `backups/` off the machine (another disk or share). Snapshots on the same disk as the live DB are not a disaster plan.
6. Confirm `file.xlsx` is **not** opened for write in Excel while people save in the app (423 lock). Read-only is fine.
7. Confirm column mapping in Settings matches the live workbook. Keep `data/app_config.json`.
8. Give people the right role: `user` edits day-to-day; `manager` creates + reports; `admin` settings/users/backup.
9. Run `python3 -m pytest tests -q` on the deploy host after install.
10. Bookmark [`docs/RECOVERY.md`](RECOVERY.md) and `./scripts/recover.sh`.

## Not this product’s job

- Multi-region clustering / Postgres. SQLite + WAL is the supported store.
- Mobile-native apps. The UI is a desktop browser.
- Replacing IM / the Excel report sheets. Those sheets are never written.

## First week of people using it

- Walk the in-app **Guide** and **Start tour**.
- Practice: Queue → open an MR → add item×supplier → Save.
- Practice a Backup now + Download zip, then restore on a test copy — not on live data first.
