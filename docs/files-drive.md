# Files page (network drive) — deployment guide

The **Files** page (`/files`) is the in-browser shared drive: users browse
folders, upload, open files on screen (tables/text preview) and download.
This page describes how to back it with a real SMB share — **with its own
service account, completely separate from the backup account.**

```
   Windows file server (192.168.100.5)
   ├── MR-Backup share   ← LINKCO.COM\mr.backup   (backups ONLY, no user access)
   └── MR-Drive share    ← LINKCO.COM\drive.mr    (Files page; user-facing)

   App server
   ├── /mnt/mr-backup  ← CIFS mount of MR-Backup with mr.backup  (backup system)
   └── /mnt/mr.drive   ← CIFS mount of MR-Drive  with drive.mr   (NETDRIVE_PATH)
```

## 1. The two accounts (this is the security boundary)

| | Backup | Files page |
| --- | --- | --- |
| Account | `LINKCO.COM\mr.backup` | `LINKCO.COM\drive.mr` |
| Share | `\\192.168.100.5\mr.backup` | `\\192.168.100.5\mr.drive` |
| Rights | Modify on mr.backup **only** | Modify on mr.drive **only** |
| Used by | backup service (nightly + manual) | every Files-page user (through the app) |
| Employee SMB access to this share | **none** | allowed (it is the user-facing share) |
| App path to the other share | none | none — enforced |

Rules (mirrored from the backup security model):

- Two accounts, never one shared; never a person's AD account; no
  interactive logon for either.
- Employees must have **no** permission on `MR-Backup`; the accounts must
  have **no** rights on each other's share.
- The app **refuses to start serving** a Files root that overlaps a backup
  destination (`NETDRIVE_PATH` vs `SMB_MOUNT_PATH` / `LOCAL_BACKUP_PATH`) —
  requests fail with a clear error instead of exposing backups.

## 2. Windows server side

1. The two service accounts on this file server: `mr.backup` (backup share)
   and `drive.mr` (files share) - no interactive login, passwords in the
   secret store.
2. Shares (UNC): `mr.backup` and `mr.drive` on 192.168.100.5.
3. Grant `mr.backup` Modify on `MR-Backup` **only**; `svc_mr_files`
   Modify on `MR-Drive` **only**. Remove "Everyone"/"Authenticated Users"
   from `MR-Backup`.

## 3. App server side (Linux)

```bash
sudo apt install cifs-utils

# credential files (each chmod 600, owned by root or the service user)
# /etc/mr-backup.cred: username=mr.backup / password=*** / domain=LINKCO.COM
# /etc/mr-files.cred:  username=drive.mr  / password=*** / domain=LINKCO.COM

sudo mkdir -p /mnt/mr-backup /mnt/mr.drive
sudo mount -t cifs //192.168.100.5/mr.backup /mnt/mr-backup \
  -o credentials=/etc/mr-backup.cred,vers=3.0,uid=$(id -u),gid=$(id -g),iocharset=utf8,noperm
sudo mount -t cifs //192.168.100.5/mr.drive /mnt/mr.drive \
  -o credentials=/etc/mr-files.cred,vers=3.0,uid=$(id -u),gid=$(id -g),iocharset=utf8,noperm
```

`/etc/fstab` (survives reboots):

```
//192.168.100.5/mr.backup  /mnt/mr-backup  cifs  credentials=/etc/mr-backup.cred,vers=3.0,uid=1000,gid=1000,iocharset=utf8,noperm,_netdev  0  0
//192.168.100.5/mr.drive   /mnt/mr.drive   cifs  credentials=/etc/mr-files.cred,vers=3.0,uid=1000,gid=1000,iocharset=utf8,noperm,_netdev  0  0
```

## 4. Application configuration (`.env`)

```env
# Backup (account 1) — see docs/backup.md
SMB_BACKUP_ENABLED=true
SMB_MODE=mount
SMB_MOUNT_PATH=/mnt/mr-backup

# Files page (account 2)
NETDRIVE_PATH=/mnt/mr.drive
```

`.env` is loaded automatically: `run.py` reads it on bare metal (real
environment variables still win), and Docker Compose reads it for
`${VAR}` substitution in `docker-compose.yml`. In Docker also uncomment the
two mount volumes (and `./backup:/app/backup`) under `volumes:`.

Leave `NETDRIVE_PATH` empty to use the app-managed folder `data/netdrive`
instead of a share (fine for getting started).

## 5. What the app enforces

- Path containment: Files requests can never escape `NETDRIVE_PATH`
  (traversal is tested).
- Backup isolation: if `NETDRIVE_PATH` equals, sits inside, or contains a
  backup destination (`SMB_MOUNT_PATH`, `LOCAL_BACKUP_PATH`, `backups/`),
  every Files request fails with
  *"NETDRIVE_PATH … overlaps a backup destination"* until fixed.
- Uploads never overwrite (auto `name (1).ext`), executables blocked,
  100 MB per file, delete/mkdir need edit/create rights; view/download need
  only view.
- Audit: uploads/deletes go through the app, never through direct user
  mounts of the backup share.

## 6. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Files page empty but share has files | `NETDRIVE_PATH` not set / wrong folder | set it to the mounted path, restart |
| `Permission denied` in uploads | drive.mr lacks Modify on mr.drive, or uid/gid mismatch | fix share ACL or mount `uid/gid` |
| `overlaps a backup destination` error | `NETDRIVE_PATH` and a backup path collide | use a separate folder/share — this is deliberate |
| Mounts vanish after reboot | no fstab entries | add the two fstab lines above |
