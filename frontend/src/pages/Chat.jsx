import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useUi } from "../context/UiContext.jsx";

export default function Chat() {
  const { user } = useAuth();
  const { toast } = useUi();
  const [threads, setThreads] = useState([]);
  const [people, setPeople] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const bottomRef = useRef(null);
  const lastId = messages.length ? messages[messages.length - 1].id : 0;

  function loadThreads() {
    return api.get("/api/chat/threads").then((d) => setThreads(d.items || []));
  }

  useEffect(() => {
    loadThreads().catch((e) => toast(e.message, "error"));
    api.get("/api/chat/people").then((d) => setPeople(d.items || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!active) return;
    api
      .get(`/api/chat/threads/${active.id}/messages`)
      .then((d) => setMessages(d.items || []))
      .catch(() => {});
  }, [active?.id]);

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      api
        .get(`/api/chat/threads/${active.id}/messages?after=${lastId}`)
        .then((d) => {
          if (d.items?.length) setMessages((prev) => [...prev, ...d.items]);
        })
        .catch(() => {});
      loadThreads().catch(() => {});
    }, 3000);
    return () => clearInterval(id);
  }, [active?.id, lastId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function send(e) {
    e.preventDefault();
    const text = body.trim();
    if (!text || !active) return;
    setBusy(true);
    try {
      const d = await api.post(`/api/chat/threads/${active.id}/messages`, { body: text });
      setMessages((prev) => [...prev, d.item]);
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
    setActive(d.item);
  }

  async function openDm(username) {
    const d = await api.post("/api/chat/threads", { kind: "direct", username });
    await loadThreads();
    setActive(d.item);
  }

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
              onClick={() => setActive(t)}
              className={`w-full text-left rounded-lg px-3 py-2 text-sm ${active?.id === t.id ? "bg-brand-700 text-white" : "hover:bg-slate-50 dark:hover:bg-white/5"}`}
            >
              <div className="font-medium truncate">{t.title}</div>
              <div className={`text-[11px] truncate ${active?.id === t.id ? "text-white/80" : "text-slate-500"}`}>{t.last_body || t.kind}</div>
            </button>
          ))}
        </div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 px-1 mt-3 mb-1">People</div>
        <div className="max-h-40 overflow-y-auto space-y-0.5">
          {people
            .filter((p) => p.username !== user?.username)
            .map((p) => (
              <button key={p.username} type="button" className="w-full text-left text-sm px-3 py-1.5 rounded-lg hover:bg-slate-50 dark:hover:bg-white/5" onClick={() => openDm(p.username)}>
                {p.full_name || p.username}
              </button>
            ))}
        </div>
      </aside>
      <section className="card flex flex-col min-h-0">
        {!active ? (
          <div className="m-auto text-sm text-slate-500 p-6">Select a channel or start a direct message.</div>
        ) : (
          <>
            <div className="px-4 py-3 border-b border-slate-200 dark:border-white/5 font-semibold">{active.title}</div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.map((m) => {
                const mine = m.username === user?.username;
                return (
                  <div key={m.id} className={`max-w-[80%] ${mine ? "ml-auto" : ""}`}>
                    <div className="text-[11px] text-slate-500 mb-0.5">
                      {m.username} · {m.created_at}
                    </div>
                    <div className={`rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${mine ? "bg-brand-700 text-white" : "bg-slate-100 dark:bg-white/5"}`}>{m.body}</div>
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
            <form onSubmit={send} className="p-3 border-t border-slate-200 dark:border-white/5 flex gap-2">
              <input value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a message… @username to ping" autoComplete="off" />
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
