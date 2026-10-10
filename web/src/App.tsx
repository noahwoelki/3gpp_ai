import { useEffect, useState } from "react";
import { fetchAvailable, streamChat, type ChatEvent } from "./api";
import ChatView from "./components/ChatView";
import FilterBar from "./components/FilterBar";
import SourcesPanel from "./components/SourcesPanel";
import SourceViewer from "./components/SourceViewer";
import type { ChatMessage, Filters, Source } from "./types";

type AssistantMessage = Extract<ChatMessage, { role: "assistant" }>;

export default function App() {
  const [tab, setTab] = useState<"ask" | "compare">("ask");
  const [available, setAvailable] = useState<Record<string, string[]>>({});
  const [filters, setFilters] = useState<Filters>({ specs: [], releases: [] });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [openSource, setOpenSource] = useState<Source | null>(null);

  useEffect(() => {
    fetchAvailable().then((data) => setAvailable(data.specs), console.error);
  }, []);

  // Applies a change to the assistant message at `index`
  const updateMessage = (index: number, change: (message: AssistantMessage) => AssistantMessage) =>
    setMessages((current) =>
      current.map((message, i) =>
        i === index && message.role === "assistant" ? change(message) : message,
      ),
    );

  const send = async (text: string) => {
    const index = messages.length + 1; // the user message goes first
    setMessages((current) => [
      ...current,
      { role: "user", text },
      { role: "assistant", text: "", steps: [], sources: [], done: false },
    ]);
    setSelected(index);
    setBusy(true);

    const onEvent = (event: ChatEvent) => {
      if (event.type === "session") setSessionId(event.session_id);
      if (event.type === "step")
        updateMessage(index, (m) => ({ ...m, steps: [...m.steps, event] }));
      if (event.type === "sources")
        updateMessage(index, (m) => ({ ...m, sources: [...m.sources, ...event.sources] }));
      if (event.type === "answer") updateMessage(index, (m) => ({ ...m, text: event.text }));
      if (event.type === "error") updateMessage(index, (m) => ({ ...m, error: event.message }));
    };

    try {
      await streamChat(text, sessionId, filters, onEvent);
    } catch (error) {
      updateMessage(index, (m) => ({ ...m, error: String(error) }));
    } finally {
      updateMessage(index, (m) => ({ ...m, done: true }));
      setBusy(false);
    }
  };

  const selectedMessage = selected !== null ? messages[selected] : null;
  const sources = selectedMessage?.role === "assistant" ? selectedMessage.sources : [];

  const tabClass = (active: boolean) =>
    `px-3 py-1.5 text-sm rounded-md ${active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-200"}`;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-4 border-b border-slate-200 bg-white px-6 py-3">
        <h1 className="text-lg font-semibold text-slate-900">SpecDelta</h1>
        <nav className="flex gap-1">
          <button className={tabClass(tab === "ask")} onClick={() => setTab("ask")}>
            Ask
          </button>
          <button className={tabClass(tab === "compare")} onClick={() => setTab("compare")}>
            Compare releases
          </button>
        </nav>
        <div className="ml-auto">
          <FilterBar available={available} filters={filters} onChange={setFilters} />
        </div>
      </header>

      {tab === "ask" ? (
        <main className="flex min-h-0 flex-1">
          <section className="min-w-0 flex-1">
            <ChatView
              messages={messages}
              busy={busy}
              selected={selected}
              onSelect={setSelected}
              onSend={send}
              onOpenSource={setOpenSource}
            />
          </section>
          <aside className="w-96 shrink-0 overflow-y-auto border-l border-slate-200 bg-white">
            <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-700">
              Sources {sources.length > 0 && <span className="text-slate-400">({sources.length})</span>}
            </h2>
            <SourcesPanel sources={sources} onOpenSource={setOpenSource} />
          </aside>
        </main>
      ) : (
        <main className="flex flex-1 items-center justify-center text-center text-slate-500">
          <div>
            <p className="text-base font-medium text-slate-700">Release comparison is coming next</p>
            <p className="mt-1 text-sm">
              Rel-17 and Rel-18 clauses side by side, with a summary of what changed per clause.
            </p>
          </div>
        </main>
      )}

      {openSource && <SourceViewer source={openSource} onClose={() => setOpenSource(null)} />}
    </div>
  );
}
