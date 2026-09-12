# First-run setup wizard

A web form that configures the whole app **before** the main server starts.
It collects every `.env` value, checks what it can (SMB credentials, folders,
mounts), creates what is missing, writes `.env` (chmod 600) and a
`setup-commands.sh` with the exact shell steps, then shuts itself down and
lets the main server start from the new `.env`.

## Run it

```bash
python3 backend/launch.py            # wizard if .env missing, then main server
python3 backend/launch.py --setup    # force the wizard (reconfigure) any time
python3 backend/launch.py --wizard-only
```

Open **http://<this-server>:8081** in a browser. Run on a trusted network
only (the wizard binds all interfaces so a laptop can reach it); it closes
itself when you press *Finish & start main server*. To let the wizard mount
the shares itself, run it with root:

```bash
sudo python3 backend/launch.py --setup
```

## What the form asks

1. **Application** — main server port (leave empty), CORS origins, JWT
   secret (Generate button).
2. **Where files are created** — local backup folder, backup share mount
   point, files share mount point, `NETDRIVE_PATH` (the folder the dashboard
   Files page serves), extra backup paths.
3. **Backup options** — enable/disable, daily/weekly/monthly retention,
   AES-256 encryption + key generator, SMB on/off, transport
   (mount / smbclient).
4. **SMB account 1 — backup share** (`svc_mr_backup`): server, share,
   domain, username, password, mount point, plus a *Mount backup share now*
   button.
5. **SMB account 2 — files share** (`svc_mr_files`): same fields for the
   user-facing Files share, plus *Mount files share now*. Point
   `NETDRIVE_PATH` (section 2) at this mount point so the Files page serves
   the share.
6. **Validate → Save → Finish**:
   - *Validate credentials & folders* runs all checks: folders created
     if missing (existence + write test if present), CIFS mount state,
     SMB account probe via `smbclient` when installed (logon failure /
     access denied / unreachable are reported exactly), retention and
     encryption-key validity, and the guard that the Files folder never
     overlaps a backup destination.
   - *Save .env* refuses to write while a hard error exists; otherwise it
     writes `.env` (600) and `setup-commands.sh` (700), backing up any
     previous `.env` to `backups/env/.env.bak-<timestamp>`.
   - *Finish* closes the wizard; `launch.py` then starts the main server
     from the new `.env`.

## Manual steps left to you

Anything needing root/Windows access is listed in `setup-commands.sh`:
the two credential files (`/etc/mr-backup.cred`, `/etc/mr-files.cred`),
the two CIFS mounts, and the two fstab lines. The SMB account checks are
automatic only when `smbclient` is installed (`sudo apt install smbclient`).

## Running on Windows (setup.bat)

On a Windows app server there is no `mount -t cifs`, `fstab` or
`smbclient` — Windows talks to shares **directly by UNC path**:

- **Backup share mount point** = `\\192.168.100.5\mr.backup`
- **Files-drive folder (NETDRIVE_PATH)** = `\\192.168.100.5\mr.files`
- **Files share mount point** = same UNC as NETDRIVE_PATH (or a mapped
  drive letter like `F:\`)

Windows reports UNC share roots and mapped drives as mounted, so the
*Backup share mount state* check turns green and backups verify
honestly. Introduce each service account to Windows once (the wizard's
`setup-commands.bat` contains exactly these lines; the password prompt
is secure):

```bat
net use \\192.168.100.5\mr.backup /user:LINKCO\svc_mr_backup * /persistent:yes
net use \\192.168.100.5\mr.files  /user:LINKCO\svc_mr_files  * /persistent:yes
```

On Windows the wizard writes `setup-commands.bat` instead of
`setup-commands.sh` (it never embeds the passwords — `net use` prompts
for them). Plain local folders such as `C:\mnt\mr-backup` are reported
as *not a share* — they are not the file server.

## The two SMB accounts (never one)

| Account | Share | Used by |
| --- | --- | --- |
| `LINKCO\svc_mr_backup` | `\\192.168.100.5\mr.backup` | backup system only — no user access |
| `LINKCO\svc_mr_files` | `\\192.168.100.5\mr.files` | Files page share (user-facing) |

Details and the Windows-side ACL setup: `docs/files-drive.md`.

## MR attachments and the network drive

On a material request, *Attach PDF or screenshot* can also save a copy to
the Files share: after attaching, choose **Also save to network drive at
[share root / folder]** (the dropdown appears when the Files share is
reachable). The MR keeps its scanned attachment as before; the copy lands
on the chosen network folder. A failed copy never blocks the MR attachment
— you get a clear toast either way.
