import { useEffect, useRef, useState } from "react";
import { specColor } from "../specs";
import type { ChatMessage, Source, Step } from "../types";
import Answer from "./Answer";

type Props = {
  messages: ChatMessage[];
  busy: boolean;
  selected: number | null; // index of the assistant message whose sources are shown
  onSelect: (index: number) => void;
  onSend: (text: string) => void;
  onOpenSource: (source: Source) => void;
};

const EXAMPLES = [
  { spec: "38.300", text: "How does cell DTX/DRX work for network energy savings?" },
  { spec: "38.101-1", text: "What is the A-MPR for NS_05 for power class 3?" },
  { spec: "38.101-1", text: "Which three-band CA configurations include n78 and n105?" },
  { spec: "38.321", text: "What does NCR mean in TS 38.321?" },
];

export default function ChatView({ messages, busy, selected, onSelect, onSend, onOpenSource }: Props) {
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  const send = (text: string) => {
    if (!text.trim() || busy) return;
    onSend(text.trim());
    setInput("");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto max-w-3xl space-y-5">
          {messages.length === 0 && <EmptyState onPick={send} />}

          {messages.map((message, index) =>
            message.role === "user" ? (
              <div key={index} className="rise flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-ink px-4 py-2.5 text-sm leading-relaxed text-paper shadow-[0_3px_0_0_var(--color-line)]">
                  {message.text}
                </div>
              </div>
            ) : (
              <div
                key={index}
                onClick={() => onSelect(index)}
                className={`rise cursor-default rounded-2xl rounded-tl-sm border bg-card px-5 py-4 transition ${
                  selected === index
                    ? "border-signal/40 shadow-[0_4px_0_0_var(--color-signal-soft)]"
                    : "border-line shadow-[0_3px_0_0_var(--color-line)]"
                }`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-display text-sm font-semibold text-ink">
                    Spec<span className="text-signal">Δ</span>
                  </span>
                  {!message.done && (
                    <span className="signal-bars">
                      <span />
                      <span />
                      <span />
                      <span />
                    </span>
                  )}
                </div>
                <Steps steps={message.steps} done={message.done} seconds={message.seconds} />
                {message.error && (
                  <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                    Something went wrong: {message.error}
                  </p>
                )}
                {message.text && (
                  <div className="rise">
                    <Answer text={message.text} sources={message.sources} onOpenSource={onOpenSource} />
                  </div>
                )}
              </div>
            ),
          )}
          <div ref={bottom} />
        </div>
      </div>

      <form
        className="px-6 pb-6 pt-2"
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
      >
        <div className="mx-auto flex max-w-3xl items-center gap-2 rounded-2xl border border-line bg-card p-1.5 pl-5 shadow-[0_4px_0_0_var(--color-line)] transition focus-within:border-ink/40">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            maxLength={2000}
            placeholder="Ask about a clause, a band, a MAC CE..."
            className="flex-1 bg-transparent py-2 text-sm outline-none placeholder:text-ink-faint"
          />
          <button
            disabled={busy || !input.trim()}
            className="group flex items-center gap-1.5 rounded-xl bg-signal px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink disabled:bg-line disabled:text-ink-faint"
          >
            Ask
            <span className="transition group-hover:translate-x-0.5">→</span>
          </button>
        </div>
      </form>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="pt-6 text-center">
      <p className="rise font-mono text-[11px] uppercase tracking-[0.25em] text-ink-faint">
        TS 38.300 · TS 38.321 · TS 38.101-1 · Rel-17 & Rel-18
      </p>
      <h2 className="rise mt-3 font-display text-5xl font-semibold leading-[1.05] tracking-tight text-ink [animation-delay:60ms]">
        3GPP spec lookup
      </h2>
      <p className="rise mx-auto mt-4 max-w-md text-sm text-ink-soft [animation-delay:120ms]">
        Questions about NR overview, MAC and UE RF requirements. Answers link to the clauses
        they are based on.
      </p>
      <div className="mt-10 grid gap-3 text-left sm:grid-cols-2">
        {EXAMPLES.map((example, i) => (
          <button
            key={example.text}
            onClick={() => onPick(example.text)}
            style={{ animationDelay: `${180 + i * 70}ms` }}
            className={`rise group relative rounded-xl border border-line bg-card px-4 py-3.5 text-sm leading-snug text-ink shadow-[0_3px_0_0_var(--color-line)] transition hover:-translate-y-1 hover:rotate-0 hover:shadow-[0_6px_0_0_var(--color-line)] ${
              i % 2 === 0 ? "-rotate-1" : "rotate-1"
            }`}
          >
            <span
              className="mb-2 inline-flex items-center gap-1.5 font-mono text-[10px] text-ink-faint"
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: specColor(example.spec) }} />
              {example.spec}
            </span>
            <span className="block group-hover:text-signal">{example.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// While the agents work, every tool call shows up as a line. Afterwards the steps fold
// into a one-line summary that can be opened again.
function Steps({ steps, done, seconds }: { steps: Step[]; done: boolean; seconds?: number }) {
  if (!done) {
    return (
      <ul className="mb-1 space-y-1.5 text-xs text-ink-soft">
        {steps.map((step, i) => {
          const current = i === steps.length - 1;
          return (
            <li key={i} className="rise flex items-start gap-2">
              <span className={`mt-px font-mono ${current ? "text-signal" : "text-spec-38321"}`}>
                {current ? "›" : "✓"}
              </span>
              <span className={current ? "text-ink" : ""}>{step.label}</span>
            </li>
          );
        })}
        {steps.length === 0 && <li className="font-display italic text-ink-faint">Working on it...</li>}
      </ul>
    );
  }
  if (steps.length === 0) return null;
  return (
    <details className="group mb-3 text-xs text-ink-faint">
      <summary className="inline-flex cursor-pointer select-none list-none items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5 font-mono transition hover:text-ink">
        <span className="transition group-open:rotate-90">›</span>
        {steps.length} steps{seconds !== undefined ? ` · ${seconds.toFixed(0)} s` : ""}
      </summary>
      <ul className="mt-2 space-y-1 border-l border-line pl-3">
        {steps.map((step, i) => (
          <li key={i}>
            <span className="font-mono text-ink-faint">{step.agent}</span>{" "}
            <span className="text-ink-soft">{step.label}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
