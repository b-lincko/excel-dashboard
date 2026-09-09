const TOKEN_KEY = "woms_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function fail(message, extra = {}) {
  const err = new Error(message);
  Object.assign(err, extra);
  return err;
}

async function parseBody(res) {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const data = await res.json();
    return { json: true, data, detail: data.detail ?? data };
  }
  return { json: false, data: null, detail: await res.text() };
}

async function request(path, { method = "GET", body, headers, raw, timeoutMs = 60000, signal } = {}) {
  const token = getToken();
  const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timer = ctrl ? window.setTimeout(() => ctrl.abort(), timeoutMs) : null;
  const onAbort = () => ctrl?.abort();
  if (ctrl && signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: {
        ...(body && !raw ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body && !raw ? JSON.stringify(body) : body,
      signal: ctrl?.signal,
    });
  } catch (e) {
    const aborted = e?.name === "AbortError";
    if (aborted && signal?.aborted) {
      throw fail("Request cancelled", { status: 0, aborted: true, cause: e });
    }
    throw fail(
      aborted
        ? "The request timed out. Wait a moment and try again."
        : "Could not reach the server. Check that Linkco MR API is running.",
      { status: 0, timeout: aborted, offline: !aborted, cause: e }
    );
  } finally {
    if (timer) window.clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
  if (res.status === 401) {
    setToken(null);
    if (!path.includes("/api/auth/login")) {
      sessionStorage.setItem("woms_auth_reason", "expired");
      window.dispatchEvent(new Event("woms:unauthorized"));
    }
  }
  if (!res.ok) {
    const parsed = await parseBody(res);
    const detail = parsed.detail;
    throw fail(typeof detail === "string" ? detail : JSON.stringify(detail), {
      status: res.status,
      detail,
    });
  }
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res;
}

function uploadWithProgress(path, formData, onProgress, timeoutMs = 15 * 60 * 1000) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.timeout = timeoutMs;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && typeof onProgress === "function") {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      const status = xhr.status;
      let data = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        data = null;
      }
      if (status === 401) {
        setToken(null);
        sessionStorage.setItem("woms_auth_reason", "expired");
        window.dispatchEvent(new Event("woms:unauthorized"));
      }
      if (status < 200 || status >= 300) {
        const detail = data?.detail ?? xhr.statusText ?? "Upload failed";
        reject(
          fail(typeof detail === "string" ? detail : JSON.stringify(detail), {
            status,
            detail,
          })
        );
        return;
      }
      if (typeof onProgress === "function") onProgress(100);
      resolve(data);
    };
    xhr.onerror = () =>
      reject(fail("Network error while uploading. Check that the API is running.", { status: 0, offline: true }));
    xhr.ontimeout = () =>
      reject(
        fail("The upload timed out. Try a smaller file or wait and retry.", {
          status: 0,
          timeout: true,
        })
      );
    xhr.send(formData);
  });
}

export const api = {
  get: (path, opts) => request(path, opts),
  post: (path, body, opts) => request(path, { method: "POST", body, ...opts }),
  put: (path, body, opts) => request(path, { method: "PUT", body, ...opts }),
  del: (path, opts) => request(path, { method: "DELETE", ...opts }),
  upload: (path, formData) => request(path, { method: "POST", body: formData, raw: true, timeoutMs: 15 * 60 * 1000 }),
  uploadWithProgress,
  blob: async (path) => {
    const token = getToken();
    const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error("Download failed");
    return res.blob();
  },
  download: async (path, filename) => {
    const blob = await api.blob(path);
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

export async function waitForJob(jobId, onTick) {
  const started = Date.now();
  while (Date.now() - started < 15 * 60 * 1000) {
    const st = await api.get(`/api/settings/jobs/${jobId}`, { timeoutMs: 20000 });
    if (typeof onTick === "function") onTick(st);
    if (st.status === "done") return st;
    if (st.status === "error") {
      throw fail(st.error || st.message || "Apply failed", { status: 400, detail: st });
    }
    await new Promise((r) => window.setTimeout(r, 400));
  }
  throw fail("Applying the file is taking too long. Check Settings in a minute.", { timeout: true, status: 0 });
}
