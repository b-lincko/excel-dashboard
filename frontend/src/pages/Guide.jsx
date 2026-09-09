import { CircleHelp, Keyboard, LifeBuoy, ListTodo, Save, Search, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTour } from "../context/TourContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";

const DAY = [
  ["1. Action queue", "Open Queue each morning. Work overdue, UNDER NTP, on hold, due soon, then missed ETAs."],
  ["2. Open the MR", "Click the row. Status, due date, supplier and PO sit in the summary strip."],
  ["3. Claim or follow", "Claim puts your name on Assign to. Follow notifies you when someone saves or chats."],
  ["4. Update and save", "Type the supplier and item names — suggestions complete them. Alt+Enter adds another vendor row. Ctrl/⌘+S saves. Close order sets CLOSED (remark required). If a colleague has the same MR open, their name shows at the top."],
];

const KEYS = [
  ["/", "Focus search from any page"],
  ["Ctrl/⌘ + K", "Command palette — jump to a page, WO, supplier or person"],
  ["g then q / w / d / c / p", "Go to Queue, Work orders, Dashboard, Chat, Purchase Approval"],
  ["n", "New material request"],
  ["j / k", "Move down / up the work-order list"],
  ["Enter", "Open the highlighted list row"],
  ["x", "Tick the highlighted row for bulk edit"],
  ["Alt + Enter", "Add another item×supplier row"],
  ["?", "Open this guide"],
  ["Ctrl/⌘ + S", "Save the open material request"],
  ["Enter / →", "Next tour step"],
  ["Esc", "Skip the tour / close palettes"],
];

export default function Guide() {
  const { start, startSigning, steps } = useTour();
  const { can } = useAuth();
  const nav = useNavigate();

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">How to use Linkco MR</h1>
          <p className="text-sm text-slate-500 mt-1">
            Live material requests live in the database. Excel is a midnight replica (and Backup now).
          </p>
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={() => {
            start();
            nav("/");
          }}
        >
          <Sparkles size={14} /> Start tour
        </button>
      </div>

      <div className="card p-5 space-y-3">
        <div className="flex items-center gap-2 font-semibold">
          <ListTodo size={16} /> Your day
        </div>
        <ol className="space-y-3">
          {DAY.map(([title, body]) => (
            <li key={title} className="text-sm">
              <div className="font-medium">{title}</div>
              <p className="text-slate-500 mt-0.5">{body}</p>
            </li>
          ))}
        </ol>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-5 space-y-2">
          <div className="flex items-center gap-2 font-semibold">
            <Search size={16} /> Find a request
          </div>
          <p className="text-sm text-slate-500">
            Header search completes WO ids, supplier names, items, people and camp sites as you type. Search on Dashboard
            or Work orders applies the filters currently set (site, status, period) and opens the matching list. Site chips
            and the Site dropdown include SH5 camps (Site - 1, 2, 3, 4A, 5, 7) and SH1 (L1–L7, LS1, LS2) as well as
            SH5-SH1, F5, Office and Accommodations. Click a chip to remove it. Save a view if you reuse the same set.
          </p>
        </div>
        <div className="card p-5 space-y-2">
          <div className="flex items-center gap-2 font-semibold">
            <Save size={16} /> Edit without duplicates
          </div>
          <p className="text-sm text-slate-500">
            Opening a row edits that record. Imports match by work-order id. If someone else saved while you were editing,
            you get a conflict — reload their values or overwrite with yours. Never two rows for the same WO.
          </p>
        </div>
      </div>

      <div className="card p-5 space-y-2">
        <div className="font-semibold">Email (Settings)</div>
        <p className="text-sm text-slate-500">
          An administrator turns on SMTP or Resend and sets a From address plus the public URL used in links. Verification
          and password-reset emails go to the address on the account. PO signature requests, Assign-to, and @mentions also
          email verified addresses. Seed logins at @woms.local are skipped. The in-app inbox still works if mail is off.
        </p>
      </div>

      <div className="card p-5 space-y-2">
        <div className="font-semibold">Purchase Approval (Daily → Purchase Approval, or g then p)</div>
        <p className="text-sm text-slate-500">
          Dedicated desk at /approvals. Assign a technician (or Unassign). Send the PDF to one, two, or three managers.
          A manager draws a digital signature — it prints on the PDF at corporate size — then sends the signed slip back
          to the sender or someone else. That person can send it to Accounts or another person. After a signature the
          slip is locked.
        </p>
        {can("po_approve") && (
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button
              type="button"
              className="btn-outline"
              onClick={() => {
                startSigning();
                nav("/approvals");
              }}
            >
              <Sparkles size={14} /> How signing works — manager tour
            </button>
            <span className="text-xs text-slate-500">
              A guided walk of the signatures desk: open the PDF, draw your signature, sign &amp; send or return with
              changes. It plays once automatically the first time you open Purchase Approval.
            </span>
          </div>
        )}
        <p className="text-sm text-slate-500">
          Assign to on the MR is the same technician list. If Purchase type is empty, pick the due date yourself
          (date only). OPEN overdue uses that due date; PLACED overdue uses ETA. Close order captures unit / price /
          total / final prices in the database.
        </p>
      </div>

      <div className="card p-5 space-y-2">
        <div className="flex items-center gap-2 font-semibold">
          <CircleHelp size={16} /> What the pages are for
        </div>
        <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <Item k="Dashboard" v="Live counts. The mind map is a 2D animated graph of those same counts — click a node, then Open list. Click a KPI to open the matching rows." />
          <Item k="Work orders" v="Every MR. Compact columns by default — add more under Columns. Bulk assign, status, remarks. Back or closing the tab asks if the MR is unsaved." />
          <Item k="Action queue" v="First item in Daily on the left. What to work now, grouped by urgency." />
          <Item k="Purchase Approval" v="Assign, send to 1–3 managers, digital-sign on the PDF, route to sender or someone else, then Accounts." />
          <Item k="Morning digest" v="Overdue / NTP / due soon by site then assignee." />
          <Item k="Suppliers / PO" v="RFQ → PO → ETA board and on-time rate." />
          <Item k="Materials" v="Who supplied an item before. Catalog tab adds and removes vendors. Aliases group spellings." />
          <Item k="Chat" v="Type @ to ping someone. Clear chat / Delete chat on the thread. A DM or MR chat is created only when you send the first message." />
          {can("settings") && <Item k="Settings" v="Seed, upload Excel, reset DB. Midnight and Backup now dump SQLite into Excel and snapshot both." />}
          {can("users") && (
            <Item k="Users" v="Create, edit, disable or delete logins. Grant extra actions. Guests get selected pages. People change their own password on Account." />
          )}
        </dl>
      </div>

      {can("backup") && (
        <div className="card p-5 space-y-2">
          <div className="font-semibold">Backups</div>
          <p className="text-sm text-slate-500">
            Create, update and delete write SQLite only. At midnight (default 00:00) and Backup now, every row is
            exported into file.xlsx and the database is snapshotted. Pairs older than 30 days move to backups/archive;
            archives older than 6 months are deleted. Download takes a zip of that pair. Upload & restore accepts
            .xlsx, .db, or a zip — confirm Restore to roll live data back. Excel-only copies do not overwrite history
            unless you Seed from Excel afterwards.
          </p>
        </div>
      )}

      <div className="card p-5 space-y-2">
        <div className="flex items-center gap-2 font-semibold">
          <LifeBuoy size={16} /> If Docker is down or data looks lost
        </div>
        <p className="text-sm text-slate-500">
          The database lives on the host as <span className="font-mono">data/woms.db</span> (not only inside the
          container). Excel is <span className="font-mono">file.xlsx</span>. Snapshots are under{" "}
          <span className="font-mono">backups/</span>.
        </p>
        <ul className="text-sm text-slate-500 list-disc pl-5 space-y-1">
          <li>
            Restart Docker: <span className="font-mono">./docker-run.sh</span> — or without Docker:{" "}
            <span className="font-mono">./run.sh --local</span>
          </li>
          <li>
            Restore a snapshot in Settings (Download / Upload & restore / Restore), or copy a paired{" "}
            <span className="font-mono">.xlsx</span> + <span className="font-mono">.db</span> from{" "}
            <span className="font-mono">backups/</span> after stopping the app.
          </li>
          <li>
            Locked out: <span className="font-mono">python3 scripts/reset_admin.py</span> then sign in and change the password immediately
          </li>
          <li>
            Full command list: <span className="font-mono">docs/RECOVERY.md</span> or{" "}
            <span className="font-mono">./scripts/recover.sh</span>
          </li>
        </ul>
      </div>

      <div className="card p-5 space-y-3" data-tour="shortcuts">
        <div className="flex items-center gap-2 font-semibold">
          <Keyboard size={16} /> Shortcuts
        </div>
        <div className="table-wrap">
          <table className="data">
            <tbody>
              {KEYS.map(([k, v]) => (
                <tr key={k} className="!cursor-default">
                  <td className="font-mono text-xs font-semibold w-36">{k}</td>
                  <td className="text-slate-500 whitespace-normal">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card p-5">
        <div className="font-semibold mb-2">Tour steps</div>
        <p className="text-sm text-slate-500 mb-3">The in-app tour walks these screens. Replay it if someone new joins.</p>
        <ol className="space-y-1 text-sm">
          {steps.map((s, i) => (
            <li key={s.id} className="flex gap-2">
              <span className="text-slate-400 w-5">{i + 1}.</span>
              <span>{s.title}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function Item({ k, v }) {
  return (
    <div>
      <dt className="font-medium">{k}</dt>
      <dd className="text-slate-500">{v}</dd>
    </div>
  );
}
