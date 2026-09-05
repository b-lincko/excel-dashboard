const TOKEN_KEY = "woms_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body, headers, raw } = {}) {
  const token = getToken();
  const res = await fetch(path, {
    method,
    headers: {
      ...(body && !raw ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body && !raw ? JSON.stringify(body) : body,
  });
  if (res.status === 401) {
    setToken(null);
    if (!path.includes("/api/auth/login")) {
      window.dispatchEvent(new Event("woms:unauthorized"));
    }
  }
  const contentType = res.headers.get("content-type") || "";
  if (!res.ok) {
    let detail = res.statusText;
    if (contentType.includes("application/json")) {
      const data = await res.json();
      detail = data.detail ?? data;
      const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = res.status;
      err.detail = detail;
      throw err;
    }
    const err = new Error(await res.text());
    err.status = res.status;
    throw err;
  }
  if (contentType.includes("application/json")) return res.json();
  return res;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  put: (path, body) => request(path, { method: "PUT", body }),
  del: (path) => request(path, { method: "DELETE" }),
  download: async (path, filename) => {
    const token = getToken();
    const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "report";
    a.click();
    URL.revokeObjectURL(url);
  },
};

export function qs(params) {
  const sp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) return;
    sp.set(k, Array.isArray(v) ? v.join(",") : String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}
