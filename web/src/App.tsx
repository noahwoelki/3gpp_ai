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
    const started = performance.now();
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
      const seconds = (performance.now() - started) / 1000;
      updateMessage(index, (m) => ({ ...m, done: true, seconds }));
      setBusy(false);
    }
  };

  const selectedMessage = selected !== null ? messages[selected] : null;
  const sources = selectedMessage?.role === "assistant" ? selectedMessage.sources : [];

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line bg-paper/85 px-6 py-3 backdrop-blur">
        <button
          onClick={() => {
            setTab("ask");
            setMessages([]);
            setSessionId(null);
            setSelected(null);
          }}
          title="New conversation"
          className="group flex items-baseline gap-0.5"
        >
          <span className="font-display text-2xl font-semibold tracking-tight text-ink">Spec</span>
          <span className="inline-block font-display text-2xl font-semibold text-signal transition group-hover:-rotate-12 group-hover:scale-110">
            Δ
          </span>
          <span className="font-display text-2xl font-semibold tracking-tight text-ink">elta</span>
        </button>

        <nav className="flex rounded-full border border-line bg-card p-0.5 text-sm">
          {(["ask", "compare"] as const).map((name) => (
            <button
              key={name}
              onClick={() => setTab(name)}
              className={`rounded-full px-3.5 py-1 transition ${
                tab === name ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
              }`}
            >
              {name === "ask" ? "Ask" : "Compare releases"}
            </button>
          ))}
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
          <aside className="hidden w-[23rem] shrink-0 flex-col border-l border-line bg-paper-deep/40 lg:flex">
            <h2 className="flex items-baseline gap-2 border-b border-line px-5 py-3">
              <span className="font-display text-base font-semibold text-ink">Sources</span>
              {sources.length > 0 && <span className="font-mono text-xs text-ink-faint">{sources.length}</span>}
            </h2>
            <div className="flex-1 overflow-y-auto">
              <SourcesPanel sources={sources} onOpenSource={setOpenSource} />
            </div>
          </aside>
        </main>
      ) : (
        <ComingSoon />
      )}

      {openSource && <SourceViewer source={openSource} onClose={() => setOpenSource(null)} />}
    </div>
  );
}

// Placeholder for the release comparison: two clause cards, slightly apart, with a delta
function ComingSoon() {
  return (
    <main className="flex flex-1 items-center justify-center px-6">
      <div className="text-center">
        <div className="relative mx-auto mb-10 h-40 w-72">
          <div className="rise absolute left-0 top-4 w-44 -rotate-6 rounded-xl border border-line bg-card p-4 text-left shadow-[0_4px_0_0_var(--color-line)]">
            <div className="font-mono text-[10px] text-ink-faint">Rel-17 · §15.4.2</div>
            <div className="mt-2 space-y-1.5">
              <div className="h-1.5 w-full rounded bg-line" />
              <div className="h-1.5 w-4/5 rounded bg-line" />
              <div className="h-1.5 w-3/5 rounded bg-line" />
            </div>
          </div>
          <div className="rise absolute right-0 top-0 w-44 rotate-3 rounded-xl border border-line bg-card p-4 text-left shadow-[0_4px_0_0_var(--color-line)] [animation-delay:120ms]">
            <div className="font-mono text-[10px] text-ink-faint">Rel-18 · §15.4.2</div>
            <div className="mt-2 space-y-1.5">
              <div className="h-1.5 w-full rounded bg-line" />
              <div className="h-1.5 w-4/5 rounded bg-marker" />
              <div className="h-1.5 w-full rounded bg-marker" />
              <div className="h-1.5 w-2/5 rounded bg-line" />
            </div>
          </div>
          <div className="pop absolute left-1/2 top-1/2 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-signal font-display text-2xl font-semibold text-white shadow-lg [animation-delay:300ms]">
            Δ
          </div>
        </div>
        <h2 className="font-display text-3xl font-semibold text-ink">Release comparison</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm text-ink-soft">
          Not built yet. Rel-17 and Rel-18 clauses side by side, with a summary of the changes.
        </p>
      </div>
    </main>
  );
}
