export const TOUR_VERSION = "v1";

export const TOUR_STEPS = [
  {
    id: "welcome",
    path: "/",
    title: "Welcome to Linkco MR",
    body: "This is the live material-request log. Search, claim, and close MRs here. Saves write the database only. Excel is updated at midnight.",
  },
  {
    id: "nav",
    path: "/",
    target: "nav-work",
    title: "Where work lives",
    body: "Dashboard is the overview. Work orders is the full list. Open, Placed, Overdue and Closed are the same list, already filtered.",
  },
  {
    id: "search",
    path: "/",
    target: "search",
    title: "Find a request from anywhere",
    body: "Type a WO number, supplier, item or person — names complete as you type. Arrow keys pick a suggestion. / focuses search. Ctrl/⌘+K opens the command palette.",
  },
  {
    id: "live",
    path: "/",
    target: "live",
    title: "Live means the database is up",
    body: "Refresh reloads records. If you see Offline, the API is down. Editors can replace the Excel backup from Upload — daily work does not need that.",
  },
  {
    id: "dashboard",
    path: "/",
    target: "dashboard",
    title: "Numbers you can click",
    body: "Every KPI and chart is counted from live records. Click a number to open the matching material requests.",
  },
  {
    id: "list",
    path: "/work-orders",
    target: "wo-list",
    page: "work_orders",
    title: "The working list",
    body: "Click a row to open it. j/k move, Enter opens, x ticks a row. Tick boxes to assign, change status, or append the same remark to several MRs at once. The Items column shows how many materials and vendors sit on that MR.",
  },
  {
    id: "filters",
    path: "/work-orders",
    target: "filters",
    page: "work_orders",
    title: "Filters stay out of the way",
    body: "They start collapsed. Open Filters when you need them. Active filters show as chips — click a chip to remove it.",
  },
  {
    id: "new",
    path: "/work-orders",
    target: "wo-new",
    page: "work_orders",
    need: "create",
    title: "New material request",
    body: "Use this when a new IM WO should exist. Existing rows are updated by WO id — the app will not create duplicates on import.",
  },
  {
    id: "record",
    path: "/work-orders/new",
    target: "wo-tabs",
    need: "create",
    title: "Details, items, activity",
    body: "Type the supplier name to complete it, then the item they can provide. Alt+Enter adds another row for a second vendor. Activity (on saved records) is chat, files and who else is looking. Don’t save this blank request unless you mean to create one.",
  },
  {
    id: "save",
    path: "/work-orders/new",
    target: "wo-save",
    need: "create",
    title: "Save sits here",
    body: "Ctrl/⌘+S also saves — to the database only. Excel is a midnight replica. If someone else has this MR open you will see their name at the top.",
  },
  {
    id: "queue",
    path: "/queue",
    target: "queue",
    page: "queue",
    title: "Start the day on the queue",
    body: "Overdue, UNDER NTP, on hold, due soon and missed ETAs. Claim a row to put your name on Assign to. Follow an MR to get notified on changes.",
  },
  {
    id: "backup",
    path: "/settings",
    target: "backup",
    page: "settings",
    need: "backup",
    title: "Excel and the database together",
    body: "Midnight and Backup now dump the database into Excel, then snapshot both. Copies older than a month go to backups/archive; six-month-old archives are deleted. Download is a zip of the pair. Excel-only leftover files do not change live history.",
  },
  {
    id: "keys",
    path: "/guide",
    target: "shortcuts",
    title: "Work without the mouse",
    body: "g then q is the queue, g then w the list, n a new MR, / search, Ctrl/⌘+K commands, ? this guide. Several people can edit at once — you get a conflict if someone saved first, and Follow notifies you of their changes.",
  },
  {
    id: "done",
    path: "/guide",
    title: "You’re ready",
    body: "Replay this tour anytime from Guide, Account, or the help button. Press ? to open this page. Daily path: Queue → open an MR → update → Save.",
  },
];

export function tourStorageKey(username) {
  return `woms.tour.${TOUR_VERSION}:${username || "anon"}`;
}

export function tourSeen(username) {
  try {
    return localStorage.getItem(tourStorageKey(username)) === "done";
  } catch {
    return false;
  }
}

export function markTourSeen(username) {
  try {
    localStorage.setItem(tourStorageKey(username), "done");
  } catch {
    /* ignore */
  }
}

export function clearTourSeen(username) {
  try {
    localStorage.removeItem(tourStorageKey(username));
  } catch {
    /* ignore */
  }
}

export function filterTourSteps(steps, { can, canPage }) {
  return steps.filter((step) => {
    if (step.need && !can(step.need)) return false;
    if (step.page && !canPage(step.page)) return false;
    return true;
  });
}

/* ---------- Manager signing tour (Purchase Approval desk) ---------- */

export const SIGNING_TOUR_VERSION = "v1";

export const SIGNING_TOUR_STEPS = [
  {
    id: "sign-welcome",
    path: "/approvals",
    target: "appr-head",
    need: "po_approve",
    title: "How to sign a purchase slip",
    body: "Purchase slips arrive here as PDFs. A dispatcher assigns the technician, the technician sends the slip to you, and you either sign it or return it with written changes. Signing locks the PO.",
  },
  {
    id: "sign-lanes",
    path: "/approvals",
    target: "appr-lanes",
    need: "po_approve",
    title: "Your lane is “Waiting for signature”",
    body: "Tabs sort every slip by its step. New slips, with technician, changes requested, waiting for signature (yours), signed, and sent to Accounts. The number on each tab is how many slips sit there.",
  },
  {
    id: "sign-pick",
    path: "/approvals",
    target: "appr-list",
    need: "po_approve",
    title: "Open a slip",
    body: "Search by WO, PO number, supplier or technician, then click a slip. Its PDF opens on the right and the action buttons appear under the summary.",
  },
  {
    id: "sign-read",
    path: "/approvals",
    target: "appr-pdf",
    need: "po_approve",
    title: "Read the PDF before you sign",
    body: "The PDF shows the purchase slip exactly as it will be filed. Download a copy if you prefer paper. Your signature prints on it at corporate size.",
  },
  {
    id: "sign-draw",
    path: "/approvals",
    target: "sign-pad",
    need: "po_approve",
    title: "Draw your signature",
    body: "Use the mouse or a finger — the line varies like ink. Clear signature starts over. What you draw is your digital signature on the document.",
  },
  {
    id: "sign-choose",
    path: "/approvals",
    target: "sign-return-to",
    need: "po_approve",
    title: "Choose who gets the signed slip",
    body: "After signing, the slip goes back to the sender by default — or pick anyone else from the list. They carry it on; it does not have to come back to you.",
  },
  {
    id: "sign-approve",
    path: "/approvals",
    target: "sign-send",
    need: "po_approve",
    title: "Sign & send locks the slip",
    body: "Once you sign, prices, suppliers and items cannot change. A confirmation asks first, then the slip moves to the person you chose. Change your mind? Return it unsigned instead.",
  },
  {
    id: "sign-return",
    path: "/approvals",
    target: "sign-return",
    need: "po_approve",
    title: "Or return it with changes",
    body: "Write what must change — a signature is not required to return it. The technician fixes the slip and sends it to you again.",
  },
  {
    id: "sign-dispatch",
    path: "/approvals",
    target: "appr-accounts",
    need: "po_dispatch",
    title: "Dispatch sends it to Accounts",
    body: "Whoever holds the signed slip can pass it to a colleague, and dispatch (or Accounts) files it in the Accounts lane. Unassign hands the slip back if the wrong technician has it.",
  },
  {
    id: "sign-done",
    path: "/approvals",
    need: "po_approve",
    title: "That’s the whole flow",
    body: "Replay this tour anytime from Guide, or the “How signing works” button on this page. Signed slips stay searchable in History.",
  },
];

export function signingTourStorageKey(username) {
  return `woms.signingTour.${SIGNING_TOUR_VERSION}:${username || "anon"}`;
}

export function signingTourSeen(username) {
  try {
    return localStorage.getItem(signingTourStorageKey(username)) === "done";
  } catch {
    return false;
  }
}

export function markSigningTourSeen(username) {
  try {
    localStorage.setItem(signingTourStorageKey(username), "done");
  } catch {
    /* ignore */
  }
}

export function clearSigningTourSeen(username) {
  try {
    localStorage.removeItem(signingTourStorageKey(username));
  } catch {
    /* ignore */
  }
}

export const TOUR_DECKS = {
  main: { steps: TOUR_STEPS, seen: tourSeen, markSeen: markTourSeen, storageKey: tourStorageKey },
  signing: {
    steps: SIGNING_TOUR_STEPS,
    seen: signingTourSeen,
    markSeen: markSigningTourSeen,
    storageKey: signingTourStorageKey,
  },
};
