"""Launcher: runs the setup wizard first (when needed), then the main server.

    python3 backend/launch.py            # wizard on :8081 if .env missing, then main server
    python3 backend/launch.py --setup    # force the wizard (reconfigure), then main server
    python3 backend/launch.py --wizard-only   # wizard and stop (do not start the server)

The wizard is a web form on port 8081 that collects every .env value,
validates SMB credentials / folders / mounts, writes .env (chmod 600),
and shuts itself down. This launcher then starts the real server
(`run.py`) from the freshly written .env.
"""
from __future__ import annotations

import runpy
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
ENV_PATH = ROOT / ".env"
WIZARD_PORT = 8081


def main() -> None:
    args = set(sys.argv[1:])
    wizard_only = "--wizard-only" in args
    force_setup = "--setup" in args or "--reconfigure" in args

    if force_setup or not ENV_PATH.is_file():
        if not ENV_PATH.is_file():
            print("[launcher] no .env found - starting the setup wizard first.")
        else:
            print("[launcher] --setup requested - starting the setup wizard (reconfigure).")
        print(f"[launcher] open the form at:  http://<this-server>:{WIZARD_PORT}")
        print("[launcher] on a trusted network only; the wizard closes itself on Finish.")

        import uvicorn

        import setup_wizard

        config = uvicorn.Config(setup_wizard.app, host="0.0.0.0", port=WIZARD_PORT, log_level="info")
        server = uvicorn.Server(config)
        setup_wizard.REQUEST_SHUTDOWN = server.should_exit
        server.run()

        if not ENV_PATH.is_file():
            print("[launcher] wizard closed without saving an .env - aborting.")
            sys.exit(1)
        print(f"[launcher] .env written - starting the main server from {ENV_PATH}")
    else:
        print(f"[launcher] using existing {ENV_PATH}")

    if wizard_only:
        print("[launcher] --wizard-only: not starting the main server.")
        return

    # fresh stdout banner separator before the main server takes over
    print("[launcher] starting main server " + "-" * 40 + f" [{uuid.uuid4().hex[:8]}]")
    sys.argv = [str(BACKEND / "run.py")]
    runpy.run_path(str(BACKEND / "run.py"), run_name="__main__")


if __name__ == "__main__":
    main()
