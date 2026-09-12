import { useCallback, useEffect, useRef, useState } from "react";
import {
  Download,
  FileText,
  FolderPlus,
  Folder,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { api } from "../lib/api.js";
import FileViewer from "../components/FileViewer.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

/**
 * Network drive (added 2026-09-12): browse the shared file area, upload,
 * open files in the browser (extracted tables / text / image+PDF preview)
 * and download. Root is configured server-side (NETDRIVE_PATH).
 */

function fmtSize(n) {
  if (!n && n !== 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`;
  return `${(n / 1073741824).toFixed(2)} GB`;
}

export default function NetDrive() {
  const { can } = useAuth();
  const { toast, ask } = useUi();
  const [dir, setDir] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState(null);
  const upRef = useRef(null);
  const canWrite = can("edit") || can("create");

  const load = useCallback(
    (d = dir) => {
      setLoading(true);
      api
        .get(`/api/netdrive${d ? `?dir=${encodeURIComponent(d)}` : ""}`)
        .then(setData)
        .catch((e) => toast(e.message || "Could not load the file area", "error"))
        .finally(() => setLoading(false));
    },
    [dir]
  );

  useEffect(() => {
    load(dir);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dir]);

  const crumbs = (data?.dir || "").split("/").filter(Boolean);

  async function upload(files) {
    if (!files?.length) return;
    setBusy(true);
    let ok = 0;
    const failed = [];
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("dir", dir);
      try {
        await api.upload("/api/netdrive/upload", fd);
        ok += 1;
      } catch (e) {
        failed.push(`${f.name}${e.message ? ` (${e.message})` : ""}`);
      }
    }
    setBusy(false);
    if (ok) toast(`${ok} file${ok > 1 ? "s" : ""} uploaded`, "success");
    if (failed.length) toast(`Not uploaded: ${failed.join(", ")}`, "error");
    load();
  }

  async function newFolder() {
    const name = window.prompt("New folder name:");
    if (!name?.trim()) return;
    try {
      await api.post("/api/netdrive/mkdir", { path: dir ? `${dir}/${name.trim()}` : name.trim() });
      load();
    } catch (e) {
      toast(e.message || "Could not create the folder", "error");
    }
  }

  async function remove(item) {
    const ok = await ask({
      title: `Delete “${item.name}”?`,
      body: item.dir ? "The folder must be empty." : "This cannot be undone.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/netdrive?path=${encodeURIComponent(dir ? `${dir}/${item.name}` : item.name)}`);
      load();
    } catch (e) {
      toast(e.message || "Delete failed", "error");
    }
  }

  function open(item) {
    const path = dir ? `${dir}/${item.name}` : item.name;
    setViewing({
      filename: item.name,
      kind: item.kind,
      size: item.size,
      contentPath: `/api/netdrive/preview?path=${encodeURIComponent(path)}`,
      downloadPath: `/api/netdrive/download?path=${encodeURIComponent(path)}`,
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="page-kicker">Shared</div>
          <h1 className="text-2xl font-bold tracking-tight">Files</h1>
          <p className="text-sm text-slate-500">
            Shared drive — browse, upload, open in the browser and download. Everyone with access sees these files.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-outline" onClick={() => load()}>
            <RefreshCw size={14} /> Refresh
          </button>
          {canWrite && (
            <>
              <button className="btn-outline" onClick={newFolder} disabled={busy}>
                <FolderPlus size={14} /> New folder
              </button>
              <input
                ref={upRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  e.target.value = "";
                  upload(files);
                }}
              />
              <button className="btn-primary" onClick={() => upRef.current?.click()} disabled={busy}>
                <Upload size={14} /> Upload
              </button>
            </>
          )}
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="px-4 py-2.5 border-b border-slate-100 dark:border-white/5 flex items-center gap-1.5 text-sm">
          <button className="text-sky-700 dark:text-sky-300 hover:underline" onClick={() => setDir("")}>
            {data?.root_name || "Drive"}
          </button>
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1.5">
              <span className="text-slate-300">/</span>
              {i === crumbs.length - 1 ? (
                <span className="font-medium">{c}</span>
              ) : (
                <button className="text-sky-700 dark:text-sky-300 hover:underline" onClick={() => setDir(crumbs.slice(0, i + 1).join("/"))}>
                  {c}
                </button>
              )}
            </span>
          ))}
        </div>
        <table className="data w-full">
          <thead>
            <tr>
              <th>Name</th>
              <th>Size</th>
              <th>Modified</th>
              <th className="w-44"></th>
            </tr>
          </thead>
          <tbody>
            {loading && !data && (
              <tr>
                <td colSpan={4} className="py-10 text-center text-slate-400">
                  <Loader2 size={18} className="animate-spin inline mr-2" /> Loading…
                </td>
              </tr>
            )}
            {(data?.items || []).map((it) => (
              <tr key={`${it.name}:${it.dir}`} className="hover:bg-slate-50 dark:hover:bg-white/5">
                <td>
                  {it.dir ? (
                    <button className="flex items-center gap-2 font-medium text-sky-800 dark:text-sky-300" onClick={() => setDir(dir ? `${dir}/${it.name}` : it.name)}>
                      <Folder size={15} className="text-amber-500" /> {it.name}
                    </button>
                  ) : (
                    <button className="flex items-center gap-2 hover:underline text-left" onClick={() => open(it)} title="View in browser">
                      <FileText size={15} className="text-slate-400 shrink-0" /> {it.name}
                    </button>
                  )}
                </td>
                <td className="text-slate-500">{it.dir ? "—" : fmtSize(it.size)}</td>
                <td className="text-slate-500">{it.mtime}</td>
                <td>
                  <div className="flex items-center gap-1.5 justify-end">
                    {!it.dir && (
                      <>
                        <button type="button" className="btn-outline !py-1 !px-2 text-xs" onClick={() => open(it)}>
                          View
                        </button>
                        <button
                          type="button"
                          className="btn-outline !py-1 !px-2 text-xs"
                          onClick={() => api.download(`/api/netdrive/download?path=${encodeURIComponent(dir ? `${dir}/${it.name}` : it.name)}`, it.name)}
                        >
                          <Download size={12} />
                        </button>
                      </>
                    )}
                    {canWrite && (
                      <button type="button" className="btn-outline !py-1 !px-2 text-xs text-rose-600 dark:text-rose-400" onClick={() => remove(it)}>
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {data && !loading && !data.items.length && (
              <tr>
                <td colSpan={4} className="py-10 text-center text-slate-400">
                  This folder is empty{canWrite ? " — upload the first file" : ""}.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {viewing && <FileViewer file={viewing} contentPath={viewing.contentPath} downloadPath={viewing.downloadPath} onClose={() => setViewing(null)} />}
    </div>
  );
}
