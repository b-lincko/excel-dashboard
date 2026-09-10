# Production deployment (nginx + uvicorn)

Topology:

```
browser ──> nginx :8000 ──┬── frontend/dist (static, pre-compressed, cached)
                          └── /api/* ──> uvicorn 127.0.0.1:8001 (loopback only)
```

The backend never binds a public interface; nginx is the only entry point.

## One-command start

```bash
cd frontend && npm install && npm run build && cd ..
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
deploy/start_production.sh          # start (deploy/start_production.sh stop stops)
```

`start_production.sh` pre-compresses assets, starts uvicorn on loopback,
waits for `/api/health`, then starts (or reloads) nginx.

## Files

| File | Purpose |
| --- | --- |
| `nginx.conf` | The reverse proxy: static serving, caching, `/api` proxy, login rate-limit, 502 JSON. |
| `proxy_params.conf` | `X-Forwarded-*` / `X-Request-ID` headers passed to the backend. |
| `precompress.sh` | Writes `.gz` next to built assets for `gzip_static`. |
| `start_production.sh` | Start/stop everything. |
| `nginx/` | nginx 1.28.3 built for THIS sandbox (`git-ignored`). On your own server install nginx from packages instead. |

## Adapting paths to another host

`nginx.conf` uses absolute paths from this workspace. On your server change:

1. `pid`, `error_log`, `access_log` → e.g. `/var/log/nginx/…`
2. `root` → your checkout's `frontend/dist`
3. the two `include /…/deploy/proxy_params.conf` lines → absolute path of this folder
4. `include mime.types;` → `include /etc/nginx/mime.types;` when installed from packages

If nginx listens on a privileged port (80/443) run it as root or adjust `user`.

## What nginx adds

- **TLS-ready entry** (terminate TLS here on a real server; the app stays HTTP to loopback)
- Long-lived `immutable` caching for hashed `/assets/*.js|css`, `no-cache` for `index.html` (deploys go live instantly)
- Pre-compressed assets (`gzip_static`) — smaller first load, zero runtime cost
- `client_max_body_size 25m` for Excel/attachment uploads, 300 s read timeout for big report downloads
- Login throttling: 20 requests/min per IP (burst 10) → HTTP 429
- JSON 502 payload instead of a raw error page when the backend restarts
- `server_tokens off`, access log with request-id and response time in `data/logs/`

## Backend changes that go with it

- `backend/run.py` binds `WOMS_HOST` (default `127.0.0.1`) / `WOMS_PORT` (default `8001`) — loopback by default, exactly what the proxy expects.
- `app/main.py` CORS defaults to **same-origin only**; set `WOMS_CORS_ORIGINS` (comma list, or `*`) only if the UI is hosted on a different origin.
- uvicorn honors `X-Forwarded-For` from the proxy (`proxy_headers` + `forwarded_allow_ips=127.0.0.1`), so logs/audit show real client IPs.

## Development mode (unchanged)

```bash
cd frontend && npm run dev     # Vite on :5173 proxies /api to 127.0.0.1:8001
cd backend && python run.py    # loopback :8001
```

## Health & logs

- App health: `GET /api/health` (through nginx or direct on :8001)
- nginx logs: `data/logs/nginx-access.log`, `data/logs/nginx-error.log`
- backend log: `data/logs/backend.log`
