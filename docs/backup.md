# Linkco MR — Dual Backup System (Local + SMB)

One application backup → **two independent copies** → **both verified** →
**independent retention** → documented restore.

```
                ┌──────────────────────┐
                │  Linkco MR backend   │
                │  (existing backup    │
                │   core + scheduler)  │
                └──────────┬───────────┘
                           │ run_dual_backup()
                           ▼
              one package: backup_<id>.zip
        (SQLite snapshot + Excel + uploads + configs
         + manifest.json with per-file SHA-256)
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      LOCAL (verified)             SMB (verified)
  $LOCAL_BACKUP_PATH/…         \\FILESERVER\MR-Backup
  Daily/ Weekly/ Monthly/      Daily/ Weekly/ Monthly/
        │                            │
        ▼                            ▼
   fast restore              disaster recovery
```

The SMB backup destination is **completely separate** from the employee file
share (`\\FILESERVER\CompanyFiles`). Different share, different service
account, different permissions. The web application never exposes either
share to users.

---

## 1. What is in a package

| Zip entry | Content | How it is taken |
| --- | --- | --- |
| `db/woms.db` | SQLite database (source of truth) | **SQLite backup API** (`database.snapshot_to`), WAL checkpointed, 3 attempts — never a raw copy of a live db |
| `excel/<file>.xlsx` | Excel replica from the **same verified pair** | existing pair backup (`excel_service.create_backup`) |
| `config/app_config.json` | column mapping + settings | file copy |
| `config/.jwt_secret` | signing secret (needed to restore logins) | file copy |
| `uploads/…` | user attachments (`data/attachments/`) | recursive copy |
| `extra/…` | optional `BACKUP_PATHS` entries | recursive copy |
| `manifest.json` | backup id, timestamps, app version, **size + SHA-256 per file**, retention | generated |

The package file name is `backup_<YYYY-MM-DD>_<HHMMSS>.zip` (`.zip.enc` when
encrypted). Next to every copy sits `<name>.sha256` and
`<name>.meta.json`. Excluded by design: `node_modules`, `.venv`, `.git`,
Docker cache, logs, OS files — the package contains application data only.

---

## 2. Workflow (implemented in `backend/app/dual_backup.py`)

```
check config → create temp dir → collect (snapshot + pair + uploads + configs)
→ build zip + manifest → SHA-256 → [optional AES-256-GCM encrypt]
→ write LOCAL Daily/ (+Weekly/+Monthly/ tier copies) → verify local checksum
→ connect SMB → copy → verify SMB copy (re-read + SHA-256 compare)
→ record status JSON + audit log → retention (independent) → cleanup temp
```

Every step emits structured log events (`BACKUP_STARTED`,
`BACKUP_ARCHIVE_CREATED`, `LOCAL_BACKUP_VERIFIED`, `SMB_BACKUP_VERIFIED`,
`SMB_BACKUP_FAILED reason=…`, `RETENTION_*`, `BACKUP_COMPLETED`) — they go to
the server log and into the per-run status JSON. **SMB credentials are never
logged.**

### Failure behaviour

Destinations are independent. If SMB fails, the local backup stays untouched
and the result is recorded:

| Local | SMB | Overall |
| --- | --- | --- |
| SUCCESS (verified) | SUCCESS (verified) | `SUCCESS` |
| SUCCESS (verified) | FAILED / verification failed | `PARTIAL_SUCCESS` |
| FAILED | SUCCESS (verified) | `PARTIAL_SUCCESS` |
| FAILED | FAILED / disabled+failed | `FAILED` |
| SUCCESS | disabled | `SUCCESS` (documented single-destination mode) |

A corrupted SMB copy (checksum mismatch) is **deleted** so it can never be
restored from, and the result is `FAILED` for that destination.

---

## 3. Local backup

Configured with `LOCAL_BACKUP_PATH` (default `./backup`, git-ignored).

* Linux: a dedicated disk/mount, e.g. `LOCAL_BACKUP_PATH=/backup`
* Windows: `LOCAL_BACKUP_PATH=D:\Application-Backups`

```
backup/
├── Daily/2026-09-12/backup_2026-09-12_020000.zip(+.sha256, .meta.json)
├── Weekly/2026-W37/…      ← first backup of the ISO week
├── Monthly/2026-09/…      ← first backup of the month
└── status/backup_….json   ← machine-readable run records (used by the UI)
```

## 4. SMB network backup (`\\FILESERVER\MR-Backup`)

Two transports (env `SMB_MODE`):

1. **`mount` (recommended)** — the share is mounted by the OS/container at
   `SMB_MOUNT_PATH`; the app just copies files. Works everywhere, no extra
   Python deps. On the Docker host:

   ```bash
   # /etc/fstab or systemd automount (credentials file root-owned 0600):
   //FILESERVER/MR-Backup  /mnt/mr-backup  cifs  credentials=/etc/mr-backup.cred,uid=1000,gid=1000,iocharset=utf8,_netdev  0  0
   ```
   ```
   # /etc/mr-backup.cred  (chmod 600)
   username=svc_mr_backup
   password=********
   domain=LINKCO
   ```
   docker-compose fragment (volume + env):
   ```yaml
   volumes:
     - ./data:/app/data
     - ./backup:/app/backup
     - /mnt/mr-backup:/mnt/mr-backup:rw
   environment:
     SMB_BACKUP_ENABLED: "true"
     SMB_MODE: mount
     SMB_MOUNT_PATH: /mnt/mr-backup
   ```

> **The #1 misconfiguration (we warn about it now):** with `SMB_MODE=mount`
> the app simply copies into `SMB_MOUNT_PATH`. If the share is **not actually
> mounted** there, that path is just a plain folder on the app server — runs
> report SUCCESS (the copy exists!) but **nothing reaches the file server**.
> The backup now emits `SMB_TARGET_NOT_MOUNTED` + a warning in the status and
> the Settings card when the target is not a real mount. Fix: mount the share
> (commands above) or switch to `SMB_MODE=smbclient`. Also note `SMB_SERVER`,
> `SMB_USERNAME` and `SMB_PASSWORD` are **only used in smbclient mode** — in
> mount mode the OS mount holds the credentials.
> `SMB_SERVER` must be the bare server name/IP (`192.168.100.5`), never the
> UNC path, and `SMB_USERNAME` is the account name (e.g. `svc_mr_backup`),
> never a share path.

2. **`smbclient`** — direct push with the `smbclient` binary
   (`SMB_SERVER`, `SMB_SHARE`, `SMB_USERNAME`, `SMB_PASSWORD`, `SMB_DOMAIN`).
   Credentials are written to a temp auth file (0600) per run and deleted
   afterwards; the password is never on the command line, in logs, or in the
   app config. Verification downloads the copy back and hashes it.
   (Retention in this mode must be enforced server-side — e.g. a scheduled
   robocopy/PowerShell cleanup on the file server; mount-mode retention runs
   from the app.)

### Required AD setup

* Dedicated service account, e.g. `LINKCO\svc_mr_backup` — **not** a person's
  account; no interactive login; password in the secret store only.
* Share `\\FILESERVER\MR-Backup` granting **modify** to `svc_mr_backup` only.
* Normal employees get **no** permission on `MR-Backup`; the service account
  gets **no** permission on `CompanyFiles`. Web-app users have no path to the
  backup share — backups are written/read only by the backend service.

---

## 5. Configuration (`.env.example`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BACKUP_ENABLED` | `true` | master switch for the dual system |
| `LOCAL_BACKUP_PATH` | `./backup` | local destination |
| `SMB_BACKUP_ENABLED` | `false` | enable the second destination |
| `SMB_MODE` | `mount` | `mount` or `smbclient` |
| `SMB_MOUNT_PATH` | `/mnt/mr-backup` | mounted share path (mount mode) |
| `SMB_SERVER` / `SMB_SHARE` | `FILESERVER` / `MR-Backup` | share (smbclient mode) |
| `SMB_DOMAIN` / `SMB_USERNAME` / `SMB_PASSWORD` | — | dedicated service account (secrets only) |
| `BACKUP_DAILY_RETENTION` | `7` | Daily tiers kept |
| `BACKUP_WEEKLY_RETENTION` | `4` | Weekly tiers kept |
| `BACKUP_MONTHLY_RETENTION` | `12` | Monthly tiers kept |
| `BACKUP_ENCRYPTION_ENABLED` | `false` | AES-256-GCM package encryption |
| `BACKUP_ENCRYPTION_KEY` | — | base64 of 32 bytes; **never** store it on the backed-up machine |
| `BACKUP_PATHS` | — | extra paths to include (`:`-separated on Linux, `;` on Windows) |

Schedule: the **existing** app schedule (Settings ▸ Backup ▸ time & days,
default `02:00`) drives the nightly run; after its verified pair is created
the dual packaging runs automatically. No extra scheduler framework was added
(matching the app's architecture).

Generate an encryption key:

```bash
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Keep the key off the server (password manager / secret store) — an encrypted
backup without the key is shrapnel.

## 6. Manual run + status

* **UI:** Settings ▸ Backup ▸ “Off-site copy (local + SMB)” — last result,
  per-destination verification, history table, **Run dual backup**.
* **API** (backup permission, admin-only):
  * `POST /api/admin/backups` → `{status, backup_id, local_backup: "verified", smb_backup: "verified"}`
  * `GET  /api/admin/backups/status` → config summary + last + history
    (no credentials in the response).
* **Status records:** `<LOCAL_BACKUP_PATH>/status/backup_<id>.json` + audit log entries (`dual_backup`).

## 7. Retention

`apply_retention` prunes `Daily/`, `Weekly/`, `Monthly/` **independently per
destination** — deleting an old local backup never deletes the SMB copy and
vice versa (smbclient mode: enforce server-side, see §4). Defaults: 7 / 4 / 12.

## 8. Restore procedure

### A. Restore the dual package (full package, offline-safe)

```bash
cd backend
# inspect first (no changes):
.venv/bin/python dual_restore.py /backup/Daily/2026-09-12/backup_2026-09-12_020000.zip --list

# restore (validates checksums, decrypts, re-hashes every file, integrity-checks
# the DB, takes a pre-restore safety pair, asks for confirmation):
.venv/bin/python dual_restore.py /backup/Daily/2026-09-12/backup_2026-09-12_020000.zip
# encrypted package: export BACKUP_ENCRYPTION_KEY=… first
# non-interactive: add --yes   · skip config files: --no-config
```

Validation before anything is overwritten: artifact checksum vs `.sha256`
sidecar → authenticated decryption → every manifest entry re-hashed →
`PRAGMA integrity_check` + work-order count on the database → explicit
confirmation. Restore target: database through the safe backup-API path, the
Excel replica atomically replaced, uploads and config files copied back.

For encrypted packages set `BACKUP_ENCRYPTION_KEY` to the same key used at
backup time. A wrong key fails loudly; nothing is modified.

### B. Restore from the classic pairs (existing UI)

Settings ▸ Backup also still lists/restores the `.xlsx`+`.db` pairs
(`POST /api/settings/backups/restore`), and `docs/RECOVERY.md` documents the
manual host-side recovery steps. The dual zip is the recommended
whole-system package (it adds uploads + configs + manifest).

---

## 9. Deployment (existing server)

1. Pull the new code; `pip install -r backend/requirements.txt`
   (adds `cryptography` for optional encryption).
2. Choose the local disk: `LOCAL_BACKUP_PATH=/backup` (create + mount it).
3. Ask IT to create the `MR-Backup` share + `svc_mr_backup` service account;
   mount it at `/mnt/mr-backup` (fstab/autofs) or install `smbclient`.
4. Fill the backup section of `.env` (or systemd `EnvironmentFile` /
   docker-compose `environment:`) — placeholders in `.env.example`.
   Never commit `.env`.
5. Docker: add the two volumes (`./backup`, the mount) + env to
   `docker-compose.yml` (fragment in §4). The container needs no extra
   privileges when using mount mode.
6. Restart the app. Press **Run dual backup** once and check both
   destinations show *verified*.
7. Decide on encryption; if enabled, store the key safely **off-server** and
   document where it lives.

## 10. Troubleshooting

| Symptom | Where to look | Typical cause |
| --- | --- | --- |
| `PARTIAL_SUCCESS`, SMB `FAILED` | status JSON `smb.reason` / server log | share not mounted, wrong credentials, network down — local copy is intact; fix and re-run |
| `SMB BACKUP VERIFICATION FAILED` | status record | transfer corruption — the bad remote copy was removed automatically; re-run |
| `BACKUP_FAILED … BACKUP_ENCRYPTION_KEY` | server log | encryption enabled without a key, or key not 32 bytes |
| `Decryption failed` during restore | restore CLI | wrong key — the package will not silently restore garbage |
| SMB `SKIPPED` | status record | `SMB_BACKUP_ENABLED=false` — enable for disaster-recovery copy |
| No weekly/monthly folder | destinations | tiers appear on the first backup of that ISO week / month |
| "SMB SUCCESS" but files don't appear on the file server | `mount -t cifs` output; status `smb.mount_warning` | `SMB_MODE=mount` without an actual mount — the app wrote to a plain local folder; mount the share or use smbclient mode |
| Restore refuses / warns | restore CLI | stop the app for a clean full restore; the DB is written through the backup API, but file.xlsx/attachments copies assume a quiet system |
