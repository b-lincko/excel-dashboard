export const TOUR_VERSION = "v1";

export const TOUR_STEPS = [
  {
    id: "welcome",
    path: "/",
    title: "Welcome to Linkco MR",
    body: "This is the live material-request log. Search, claim, and close MRs here. Each save writes the database first, then copies a backup to Excel.",
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
    body: "Ctrl/⌘+S also saves. The database is written first. If Excel is locked, the record is still kept and you can retry the backup. If someone else has this MR open you will see their name at the top.",
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
    body: "Every backup copies SQLite plus Excel — Backup now, the schedule, and each save. Download is a zip of both. Restore rolls both back when a .db pair exists. Excel-only leftover files do not change live history.",
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
