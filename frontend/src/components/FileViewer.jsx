import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Copy, Download, FileText, Loader2, Table2, X } from "lucide-react";
import { api } from "../lib/api.js";

/**
 * On-screen attachment viewer (added 2026-09-12).
 * Click an attachment -> modal with the extracted content: tables you can
 * copy, raw text you can select, or an image/PDF preview when there is no
 * extractable text. Download stays one click away.
 */

function toTSV(rows) {
  return (rows || [])
    .map((row) => (row || []).map((cell) => String(cell ?? "").replace(/\t/g, " ")).join("\t"))
    .join("\n");
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    ta.remove();
    return ok;
  }
}

function CopyBtn({ text, label = "Copy", className = "btn-outline !py-1 !px-2 text-xs" }) {
  const [done, setDone] = useState(false);
  if (!text || !text.trim()) return null;
  return (
    <button
      type="button"
      className={className}
      onClick={async () => {
        if (await copyText(text)) {
          setDone(true);
          window.setTimeout(() => setDone(false), 1500);
        }
      }}
    >
      {done ? "Copied!" : (<><Copy size={12} /> {label}</>)}
    </button>
  );
}

function ExtractedTable({ rows, caption }) {
  if (!rows || rows.length < 1) return null;
  const [head, ...body] = rows;
  const headerLooksReal = head.filter((c) => String(c || "").trim()).length > 1;
  const cols = Math.max(...rows.map((r) => (r || []).length));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{caption}</div>
        <CopyBtn text={toTSV(rows)} label="Copy table" />
      </div>
      <div className="overflow-auto max-h-72 rounded-lg border border-slate-200 dark:border-white/10">
        <table className="data w-full text-xs">
          <thead>
            <tr>
              {(headerLooksReal ? head : rows[0].map((_, i) => `Col ${i + 1}`)).map((c, i) => (
                <th key={i} className="sticky top-0 bg-slate-50 dark:bg-ink-800">{String(c || "").trim() || "—"}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(headerLooksReal ? body : rows).map((row, ri) => (
              <tr key={ri}>
                {Array.from({ length: cols }, (_, ci) => (
                  <td key={ci} className="whitespace-pre-wrap">{String(row[ci] ?? "").trim() || "—"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function FileViewer({ file, onClose, contentPath, downloadPath }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [blobUrl, setBlobUrl] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!file) return undefined;
    let cancelled = false;
    let url = "";
    setLoading(true);
    setErr("");
    api
      .get(contentPath || `/api/files/${file.id}/content`)
      .then(async (d) => {
        if (cancelled) return;
        setData(d);
        const kind = d?.item?.kind;
        const noText = !d?.extract?.ok || (!d.extract.text && !(d.extract.tables || []).length && !(d.extract.sheets || []).length);
        if (kind === "screenshot" || (kind === "pdf" && noText)) {
          const blob = await api.blob(downloadPath || `/api/files/${file.id}`);
          url = URL.createObjectURL(blob);
          setBlobUrl(url);
        }
        setLoading(false);
      })
      .catch((e) => {
        if (!cancelled) {
          setErr(e.message || "Could not load the file preview.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [file?.id, contentPath, downloadPath]);

  if (!file) return null;
  const extract = data?.extract;
  const tables = [...(extract?.tables || []), ...(extract?.sheets || []).map((s) => ({ rows: s.rows, sheet: s.name }))];
  const isImage = data?.item?.kind === "screenshot";
  const isPdf = data?.item?.kind === "pdf";
  const showPreview = (isImage || (isPdf && blobUrl)) && blobUrl && (!extract?.ok || (!extract.text && !tables.length));

  return createPortal(
    <div
      className="fixed inset-0 z-[130] grid place-items-center p-3 sm:p-6 bg-slate-900/60 backdrop-blur-[2px]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div role="dialog" aria-modal="true" aria-label={`Preview ${file.filename}`} className="w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl bg-white dark:bg-ink-900 border border-slate-200 dark:border-white/10 shadow-2xl">
        <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-slate-100 dark:border-white/5">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-slate-400">Attachment preview</div>
            <div className="font-bold truncate flex items-center gap-2">
              <FileText size={15} className="shrink-0 text-sky-700 dark:text-sky-300" /> {file.filename}
            </div>
            {extract?.ok && (
              <div className="text-xs text-slate-500 mt-0.5">
                Scanned: {extract.words ? `${extract.words} words` : ""}{extract.words && tables.length ? " · " : ""}{tables.length ? `${tables.length} table${tables.length > 1 ? "s" : ""}` : ""}
                {extract.engine ? ` · ${extract.engine}` : ""}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button type="button" className="btn-outline !py-1.5 text-xs" onClick={() => api.download(downloadPath || `/api/files/${file.id}`, file.filename)}>
              <Download size={13} /> Download
            </button>
            <button type="button" className="btn-ghost !px-2" onClick={onClose} aria-label="Close">
              <X size={17} />
            </button>
          </div>
        </div>

        <div className="overflow-auto px-5 py-4 space-y-5">
          {loading && (
            <div className="grid place-items-center py-12 text-slate-500 text-sm gap-2">
              <Loader2 size={22} className="animate-spin" /> Reading the file…
            </div>
          )}
          {err && !loading && <div className="rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{err}</div>}

          {!loading && !err && (
            <>
              {extract?.message && (
                <div className="rounded-lg bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">{extract.message}</div>
              )}

              {tables.map((t, i) => (
                <ExtractedTable key={i} rows={t.rows} caption={t.sheet ? `Sheet: ${t.sheet}` : t.page ? `Table on page ${t.page}` : `Table ${i + 1}`} />
              ))}

              {extract?.text && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Text — select and copy</div>
                    <CopyBtn text={extract.text} label="Copy text" />
                  </div>
                  <pre className="whitespace-pre-wrap text-sm bg-slate-50 dark:bg-white/5 rounded-lg border border-slate-200 dark:border-white/10 p-3 max-h-80 overflow-auto select-text">{extract.text}</pre>
                </div>
              )}

              {showPreview && isImage && <img src={blobUrl} alt={file.filename} className="max-h-[60vh] w-auto rounded-lg border border-slate-200 dark:border-white/10 mx-auto" />}
              {showPreview && isPdf && <iframe title={file.filename} src={blobUrl} className="w-full h-[60vh] rounded-lg border border-slate-200 dark:border-white/10" />}

              {!extract?.ok && !showPreview && !extract?.message && (
                <div className="text-sm text-slate-500">No on-screen preview for this file — use Download.</div>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t border-slate-100 dark:border-white/5 flex items-center justify-between text-xs text-slate-400">
          <span className="flex items-center gap-1.5">{tables.length ? <Table2 size={12} /> : null} Select any text to copy, or use the copy buttons.</span>
          <button type="button" className="btn-outline !py-1 !px-2.5" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>,
    document.body
  );
}
