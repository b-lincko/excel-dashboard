import { useRef, useState } from "react";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

export default function ImportData() {
  const { can } = useAuth();
  const { toast } = useUi();
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const d = await api.upload("/api/transfer/import", fd);
      setResult(d);
      toast(d.message || `Imported ${d.created || 0} new, ${d.updated || 0} updated`, "success");
      window.dispatchEvent(new CustomEvent("woms:data", { detail: d.sync }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function exportCsv() {
    try {
      await api.download("/api/transfer/export.csv", "linkco-mr-export.csv");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Import / transfer</h1>
        <p className="text-sm text-slate-500">
          Excel remains the source of truth. CSV and Excel files are mapped onto existing columns and matched by work-order id (no duplicates). PDFs are attached to a matching WO or imported as a new remark.
        </p>
      </div>
      {error && <div className="rounded-xl bg-rose-50 text-rose-800 px-4 py-3 text-sm">{error}</div>}
      <div className="card p-5 space-y-3">
        <div className="font-semibold">Export current data</div>
        <p className="text-sm text-slate-500">Download a CSV of every mapped field from the live workbook (also cached in SQLite for faster reads).</p>
        <button className="btn-outline" type="button" onClick={exportCsv}>
          Download CSV
        </button>
      </div>
      {can("edit") && (
        <div className="card p-5 space-y-3">
          <div className="font-semibold">Import Excel, CSV or PDF</div>
          <p className="text-sm text-slate-500">
            Headers can be the original Excel names (IM Work Order #, STATUS, …) or internal names. Existing unique WO ids are updated; new ones are appended. A backup is written first.
          </p>
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv,.pdf" className="hidden" onChange={onFile} />
          <button className="btn-primary" type="button" disabled={busy} onClick={() => fileRef.current?.click()}>
            {busy ? "Importing…" : "Choose file"}
          </button>
        </div>
      )}
      {result && (
        <div className="card p-5 text-sm space-y-1">
          <div>
            Created: <strong>{result.created ?? 0}</strong>
          </div>
          <div>
            Updated: <strong>{result.updated ?? 0}</strong>
          </div>
          <div>
            Skipped: <strong>{result.skipped ?? 0}</strong>
          </div>
          {result.attached ? <div>PDF attached: {result.attached}</div> : null}
          {result.total != null && <div>Workbook rows now: {result.total}</div>}
          {(result.errors || []).length > 0 && (
            <ul className="text-rose-600 list-disc ml-5">
              {result.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
