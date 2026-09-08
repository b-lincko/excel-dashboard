#!/usr/bin/env python3
"""Reset or create an admin login. Run from the repo root (app stopped or running).

  python3 scripts/reset_admin.py
  python3 scripts/reset_admin.py --username admin --password admin123
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app import database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset or create an admin user in data/woms.db")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--full-name", default="System Administrator")
    args = parser.parse_args()
    database.init_db()
    user = database.get_user_by_username(args.username)
    if user:
        database.update_user(int(user["id"]), password=args.password, role="admin", is_active=1)
        print(f"Updated {args.username} → admin (active). Sign in with the password you passed.")
    else:
        database.create_user(args.username, args.full_name, "", args.password, "admin")
        print(f"Created {args.username} as admin. Sign in with the password you passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
