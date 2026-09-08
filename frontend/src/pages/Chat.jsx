import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";
import MentionBox from "../components/MentionBox.jsx";

function mergeMessages(prev, incoming) {
  if (!incoming?.length) return prev;
  const seen = new Set(prev.map((m) => m.id));
  const extra = incoming.filter((m) => m?.id != null && !seen.has(m.id));
  return extra.length ? [...prev, ...extra] : prev;
}

function dmTitleHas(thread, username) {
  if (!thread || thread.kind !== "direct") return false;
  return String(thread.title || "")
    .split("·")
    .map((s) => s.trim().toLowerCase())
    .includes(String(username || "").toLowerCase());
}

export default function Chat() {
  const { user } = useAuth();
  const { toast, ask } = useUi();
  const [params] = useSearchParams();
  const [threads, setThreads] = useState([]);
  const [people, setPeople] = useState([]);
  const [active, setActive] = useState(null);
  const [draft, setDraft] = useState(null);
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const bottomRef = useRef(null);
  const lastIdRef = useRef(0);
  const activeIdRef = useRef(null);

  function loadThreads() {
    return api.get("/api/chat/threads").then((d) => {
      setThreads(d.items || []);
      return d;
    });
  }

  const threadWanted = Number(params.get("thread") || 0);

  useEffect(() => {
    loadThreads()
      .then((d) => {
        if (threadWanted) {
          const hit = (d?.items || []).find((t) => Number(t.id) === threadWanted);
          if (hit) {
            setDraft(null);
            setActive(hit);
          }
        }
      })
      .catch((e) => toast(e.message, "error"));
    api.get("/api/chat/people").then((d) => setPeople(d.items || [])).catch(() => {});
  }, [threadWanted]);

  useEffect(() => {
    activeIdRef.current = active?.id || null;
    lastIdRef.current = 0;
    if (!active) {
      if (!draft) setMessages([]);
      return;
    }
    api
      .get(`/api/chat/threads/${active.id}/messages`)
      .then((d) => {
        const items = d.items || [];
        setMessages(items);
        lastIdRef.current = items.length ? items[items.length - 1].id : 0;
      })
      .catch(() => {});
  }, [active?.id]);

  useEffect(() => {
    const id = setInterval(() => {
      loadThreads().catch(() => {});
      const tid = activeIdRef.current;
      if (!tid) return;
      api
        .get(`/api/chat/threads/${tid}/messages?after=${lastIdRef.current}`)
        .then((d) => {
          if (d.items?.length) {
            setMessages((prev) => mergeMessages(prev, d.items));
            lastIdRef.current = d.items[d.items.length - 1].id;
          }
        })
        .catch(() => {});
    }, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function send(e) {
    e.preventDefault();
    const text = body.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      let thread = active;
      if (!thread && draft?.username) {
        const d = await api.post("/api/chat/threads", { kind: "direct", username: draft.username });
        thread = d.item;
        setActive(thread);
        setDraft(null);
      }
      if (!thread) return;
      const d = await api.post(`/api/chat/threads/${thread.id}/messages`, { body: text });
      setMessages((prev) => mergeMessages(prev, d.item ? [d.item] : []));
      if (d.item?.id) lastIdRef.current = d.item.id;
      setBody("");
      loadThreads();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function newChannel() {
    const name = title.trim();
    if (!name) return;
    const d = await api.post("/api/chat/threads", { kind: "channel", title: name });
    setTitle("");
    await loadThreads();
    setDraft(null);
    setActive(d.item);
  }

  function openDm(username) {
    const existing = threads.find((t) => dmTitleHas(t, username));
    if (existing) {
      setDraft(null);
      setActive(existing);
      return;
    }
    setActive(null);
    setMessages([]);
    setDraft({ username, title: username });
  }

  async function clearChat() {
    if (!active) return;
    const ok = await ask({
      title: "Clear this chat?",
      body: "All messages in this conversation will be removed. The thread stays.",
      confirmLabel: "Clear chat",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/chat/threads/${active.id}/messages`);
      setMessages([]);
      lastIdRef.current = 0;
      loadThreads();
      toast("Chat cleared", "success");
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function deleteChat() {
    if (!active) return;
    const general = active.kind === "channel" && String(active.title || "").toLowerCase() === "general";
    if (general) {
      toast("The General channel cannot be deleted", "error");
      return;
    }
    const ok = await ask({
      title: "Delete this chat?",
      body: "The conversation and its messages are removed. It will not reappear until someone starts it again.",
      confirmLabel: "Delete chat",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/chat/threads/${active.id}`);
      setActive(null);
      setMessages([]);
      setDraft(null);
      loadThreads();
      toast("Chat deleted", "success");
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function deleteMessage(m) {
    if (!active || !m?.id) return;
    const ok = await ask({
      title: "Delete this message?",
      body: m.body,
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/chat/threads/${active.id}/messages/${m.id}`);
      setMessages((prev) => prev.filter((x) => x.id !== m.id));
    } catch (err) {
      toast(err.message, "error");
    }
  }

  const heading = active?.title || (draft ? `New message to ${draft.title}` : "");
  const canSend = Boolean(active || draft);
  const isGeneral = active?.kind === "channel" && String(active?.title || "").toLowerCase() === "general";

  return (
    <div className="h-[calc(100vh-8rem)] min-h-[480px] grid md:grid-cols-[260px_1fr] gap-4">
      <aside className="card p-3 flex flex-col min-h-0">
        <div className="font-semibold px-1 mb-2">Chat</div>
        <div className="flex gap-2 mb-3">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New channel" />
          <button className="btn-outline !px-2" type="button" onClick={newChannel}>
            Add
          </button>
        </div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 px-1 mb-1">Threads</div>
        <div className="flex-1 overflow-y-auto space-y-1">
          {threads.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => {
                setDraft(null);
                setActive(t);
              }}
              className={`w-full text-left rounded-lg px-3 py-2 text-sm ${active?.id === t.id ? "bg-brand-700 text-white" : "hover:bg-slate-50 dark:hover:bg-white/5"}`}
            >
              <div className="font-medium truncate">{t.title}</div>
              <div className={`text-[11px] truncate ${active?.id === t.id ? "text-white/80" : "text-slate-500"}`}>
                {t.kind === "work_order" ? "Work order · " : t.kind === "direct" ? "DM · " : ""}
                {t.last_body || t.kind}
              </div>
            </button>
          ))}
        </div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 px-1 mt-3 mb-1">People</div>
        <div className="max-h-40 overflow-y-auto space-y-0.5">
          {people
            .filter((p) => p.username !== user?.username)
            .map((p) => (
              <button
                key={p.username}
                type="button"
                className={`w-full text-left text-sm px-3 py-1.5 rounded-lg hover:bg-slate-50 dark:hover:bg-white/5 ${draft?.username === p.username ? "bg-slate-100 dark:bg-white/10" : ""}`}
                onClick={() => openDm(p.username)}
              >
                {p.full_name || p.username}
              </button>
            ))}
        </div>
      </aside>
      <section className="card flex flex-col min-h-0">
        {!canSend ? (
          <div className="m-auto text-sm text-slate-500 p-6">
            Select a channel or a person. A conversation is created only when you send the first message.
          </div>
        ) : (
          <>
            <div className="px-4 py-3 border-b border-slate-200 dark:border-white/5 flex items-center justify-between gap-3">
              <span className="font-semibold truncate">{heading}</span>
              <div className="flex items-center gap-2 shrink-0">
                {active?.kind === "work_order" && active.record_id && (
                  <Link className="text-xs font-medium text-brand-700 dark:text-cyan-300" to={`/work-orders/${encodeURIComponent(active.record_id)}`}>
                    Open MR
                  </Link>
                )}
                {active && (
                  <button type="button" className="btn-ghost !px-2 !py-1 text-xs" onClick={clearChat}>
                    Clear chat
                  </button>
                )}
                {active && !isGeneral && (
                  <button type="button" className="btn-ghost !px-2 !py-1 text-xs text-rose-600" onClick={deleteChat}>
                    Delete chat
                  </button>
                )}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {!active && draft && (
                <div className="text-sm text-slate-500">Write a message to start this conversation with {draft.title}.</div>
              )}
              {messages.map((m) => {
                const mine = m.username === user?.username;
                return (
                  <div key={m.id} className={`max-w-[80%] group ${mine ? "ml-auto" : ""}`}>
                    <div className="text-[11px] text-slate-500 mb-0.5 flex items-center gap-2">
                      <span>
                        {m.username} · {m.created_at}
                      </span>
                      {(mine || user?.role === "admin") && (
                        <button type="button" className="opacity-0 group-hover:opacity-100 text-rose-600" onClick={() => deleteMessage(m)}>
                          Delete
                        </button>
                      )}
                    </div>
                    <div className={`rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${mine ? "bg-brand-700 text-white" : "bg-slate-100 dark:bg-white/5"}`}>{m.body}</div>
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
            <form onSubmit={send} className="p-3 border-t border-slate-200 dark:border-white/5 flex gap-2">
              <MentionBox value={body} onChange={setBody} people={people} placeholder="Write a message… type @ to mention" className="flex-1" />
              <button className="btn-primary" disabled={busy || !body.trim()}>
                Send
              </button>
            </form>
          </>
        )}
      </section>
    </div>
  );
}
