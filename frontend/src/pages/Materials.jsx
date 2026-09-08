import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

const TABS = [
  { id: "directory", label: "Directory" },
  { id: "suggest", label: "Suggestions" },
  { id: "duplicates", label: "Duplicate names" },
  { id: "add", label: "Add supplier" },
];

export default function Materials({ mode = "directory" }) {
  const { can } = useAuth();
  const { toast, ask } = useUi();
  const [tab, setTab] = useState(mode === "suggest" ? "suggest" : "directory");
  const [by, setBy] = useState("material");
  const [q, setQ] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [clusters, setClusters] = useState([]);
  const [aliases, setAliases] = useState([]);
  const [picked, setPicked] = useState({});
  const [form, setForm] = useState({ name: "", phone: "", email: "", contact: "", lead_time_days: "", notes: "", items: "" });

  useEffect(() => {
    setTab(mode === "suggest" ? "suggest" : tab);
  }, [mode]);

  useEffect(() => {
    if (tab !== "duplicates") return;
    api
      .get("/api/catalog/duplicates")
      .then((d) => {
        setClusters(d.items || []);
        setAliases(d.aliases || []);
      })
      .catch((e) => setError(e.message));
  }, [tab]);

  async function search(e) {
    e?.preventDefault?.();
    const query = q.trim();
    if (!query) {
      setResult({ items: [], total: 0, query: "" });
      return;
    }
    setBusy(true);
    setError("");
    try {
      const path =
        tab === "suggest"
          ? `/api/catalog/suggest?q=${encodeURIComponent(query)}`
          : `/api/catalog/materials?by=${encodeURIComponent(by)}&q=${encodeURIComponent(query)}`;
      setResult(await api.get(path));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function addSupplier(e) {
    e.preventDefault();
    const name = form.name.trim();
    if (!name) return;
    setBusy(true);
    setError("");
    try {
      const items = form.items
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      await api.post("/api/catalog/suppliers", {
        name,
        phone: form.phone,
        email: form.email,
        contact: form.contact,
        lead_time_days: form.lead_time_days ? Number(form.lead_time_days) : null,
        notes: form.notes,
        items,
      });
      toast(`Supplier “${name}” saved with ${items.length} item${items.length === 1 ? "" : "s"}`, "success");
      setForm({ name: "", phone: "", email: "", contact: "", lead_time_days: "", notes: "", items: "" });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function mergeCluster(cluster, writeExcel) {
    const canonical = (picked[cluster.canonical] || cluster.canonical).trim();
    const aliasesToMerge = (cluster.names || []).filter((n) => n.toLowerCase() !== canonical.toLowerCase());
    if (!aliasesToMerge.length) return;
    const ok = await ask({
      title: writeExcel ? "Rewrite Excel supplier names?" : "Save alias mapping?",
      body: writeExcel
        ? `Rows whose Supplier Name is exactly one of:\n${aliasesToMerge.join("\n")}\nwill be rewritten to “${canonical}”. Combined cells (A & B) are left alone. A backup is written first.`
        : `“${canonical}” will be used in search and suggestions. Excel cells stay as they are until you confirm a rewrite.`,
      confirmLabel: writeExcel ? "Write Excel" : "Save aliases",
      danger: writeExcel,
    });
    if (!ok) return;
    setBusy(true);
    try {
      const d = await api.post("/api/catalog/suppliers/merge", {
        canonical,
        aliases: aliasesToMerge,
        write_excel: writeExcel,
      });
      toast(
        writeExcel ? `Excel updated · ${d.excel_updated} row${d.excel_updated === 1 ? "" : "s"}` : "Aliases saved",
        "success"
      );
      const next = await api.get("/api/catalog/duplicates");
      setClusters(next.items || []);
      setAliases(next.aliases || []);
      if (writeExcel) window.dispatchEvent(new CustomEvent("woms:data"));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const title = mode === "suggest" ? "Supplier suggestions" : "Materials & suppliers";
  const hint =
    tab === "suggest"
      ? "Type an item. Suppliers who already provided it come from Excel history, line items, and the catalog."
      : tab === "directory"
        ? "Search a material to see who supplied it, or a supplier to see what they have provided."
        : tab === "duplicates"
          ? "Excel has many spellings of the same vendor (W.L.L vs WLL, missing letters). Aliases group them without rewriting the workbook until you confirm."
          : "New suppliers and the items they can provide live in the app catalog. Excel still has one Supplier Name cell per MR.";

  return (
    <div className="space-y-5 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <p className="text-sm text-slate-500">{hint}</p>
      </div>
      {error && <div className="text-sm text-rose-600">{error}</div>}

      <div className="flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
              tab === t.id ? "bg-brand-700 text-white" : "bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300"
            }`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {(tab === "directory" || tab === "suggest") && (
        <form onSubmit={search} className="card p-4 space-y-3">
          {tab === "directory" && (
            <div className="flex flex-wrap gap-2 text-sm">
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" className="!w-auto" checked={by === "material"} onChange={() => setBy("material")} />
                Material → suppliers
              </label>
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" className="!w-auto" checked={by === "supplier"} onChange={() => setBy("supplier")} />
                Supplier → materials
              </label>
            </div>
          )}
          <div className="flex gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={tab === "suggest" || by === "material" ? "Item name, e.g. UPS module" : "Supplier name"}
              autoFocus
            />
            <button className="btn-primary shrink-0" disabled={busy}>
              {busy ? "Searching…" : "Search"}
            </button>
          </div>
        </form>
      )}

      {(tab === "directory" || tab === "suggest") && result && (
        <div className="space-y-3">
          <div className="text-xs text-slate-500">
            {result.total} match{result.total === 1 ? "" : "es"}
            {result.query ? ` for “${result.query}”` : ""}
          </div>
          {(result.items || []).map((row) => (
            <div key={row.supplier} className="card p-4 space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{row.supplier}</div>
                  {!!row.aliases?.length && <div className="text-[11px] text-slate-500">Also as: {row.aliases.join(" · ")}</div>}
                </div>
                <div className="text-xs text-slate-500 whitespace-nowrap">
                  {row.work_order_count} MR{row.work_order_count === 1 ? "" : "s"} · {row.hit_count} hit{row.hit_count === 1 ? "" : "s"}
                </div>
              </div>
              <ul className="text-sm space-y-1">
                {(row.materials || []).slice(0, 8).map((m) => (
                  <li key={m} className="text-slate-700 dark:text-slate-200">
                    {m}
                  </li>
                ))}
              </ul>
              {!!row.sources?.length && <div className="text-[11px] uppercase tracking-wider text-slate-400">{row.sources.join(" · ")}</div>}
            </div>
          ))}
          {!result.items?.length && <div className="card p-8 text-center text-sm text-slate-500">No matches in Excel, line items, or the catalog.</div>}
        </div>
      )}

      {tab === "duplicates" && (
        <div className="space-y-3">
          {!!aliases.length && (
            <div className="text-xs text-slate-500">
              Saved aliases: {aliases.slice(0, 8).map((a) => `${a.alias} → ${a.canonical}`).join(" · ")}
              {aliases.length > 8 ? "…" : ""}
            </div>
          )}
          {clusters.map((c) => (
            <div key={c.canonical} className="card p-4 space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[200px]">
                  <label className="lbl">Canonical name</label>
                  <input value={picked[c.canonical] ?? c.canonical} onChange={(e) => setPicked({ ...picked, [c.canonical]: e.target.value })} />
                </div>
                <div className="text-xs text-slate-500 pb-2">{c.total} Excel rows across {c.names.length} spellings</div>
              </div>
              <ul className="text-sm space-y-1">
                {c.names.map((n) => (
                  <li key={n} className="flex justify-between gap-3">
                    <span>{n}</span>
                    <span className="text-slate-500">{c.counts?.[n] || 0}</span>
                  </li>
                ))}
              </ul>
              {can("edit") && (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn-outline" disabled={busy} onClick={() => mergeCluster(c, false)}>
                    Save aliases
                  </button>
                  <button type="button" className="btn-primary" disabled={busy} onClick={() => mergeCluster(c, true)}>
                    Rewrite matching Excel cells
                  </button>
                </div>
              )}
            </div>
          ))}
          {!clusters.length && <div className="card p-8 text-center text-sm text-slate-500">No close duplicate supplier names found.</div>}
        </div>
      )}

      {tab === "add" && (
        <form onSubmit={addSupplier} className="card p-5 grid md:grid-cols-2 gap-3">
          <div className="md:col-span-2">
            <label className="lbl">Supplier name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required disabled={!can("edit")} />
          </div>
          <div>
            <label className="lbl">Phone</label>
            <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} disabled={!can("edit")} />
          </div>
          <div>
            <label className="lbl">Email</label>
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} disabled={!can("edit")} />
          </div>
          <div>
            <label className="lbl">Contact</label>
            <input value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} disabled={!can("edit")} />
          </div>
          <div>
            <label className="lbl">Lead time (days)</label>
            <input type="number" value={form.lead_time_days} onChange={(e) => setForm({ ...form, lead_time_days: e.target.value })} disabled={!can("edit")} />
          </div>
          <div className="md:col-span-2">
            <label className="lbl">Notes</label>
            <textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} disabled={!can("edit")} />
          </div>
          <div className="md:col-span-2">
            <label className="lbl">Items they can provide (one per line)</label>
            <textarea
              rows={6}
              value={form.items}
              onChange={(e) => setForm({ ...form, items: e.target.value })}
              placeholder={"UPS module\nAHU belts\nFilters"}
              disabled={!can("edit")}
            />
          </div>
          {can("edit") && (
            <div className="md:col-span-2">
              <button className="btn-primary" disabled={busy || !form.name.trim()}>
                {busy ? "Saving…" : "Save supplier"}
              </button>
            </div>
          )}
        </form>
      )}

      {mode !== "suggest" && tab === "directory" && (
        <p className="text-xs text-slate-400">
          Need a vendor for one item? Open <Link to="/supplier-suggest" className="underline">supplier suggestions</Link>.
        </p>
      )}
    </div>
  );
}
