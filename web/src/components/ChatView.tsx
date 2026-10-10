import { useEffect, useRef, useState } from "react";
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
  "How does cell DTX/DRX work for network energy savings?",
  "What is the A-MPR for NS_05 for power class 3?",
  "Which three-band CA configurations include n78 and n105?",
  "What does NCR mean in TS 38.321?",
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
      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {messages.length === 0 && (
          <div className="mx-auto mt-10 max-w-xl text-center">
            <h2 className="text-lg font-semibold text-slate-800">Ask about TS 38.300, 38.321 and 38.101-1</h2>
            <p className="mt-1 text-sm text-slate-500">Answers cite the clauses they come from.</p>
            <div className="mt-6 grid gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => send(example)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-left text-sm text-slate-700 hover:border-blue-400"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="flex justify-end">
              <div className="max-w-[80%] rounded-lg bg-blue-600 px-4 py-2 text-sm text-white">{message.text}</div>
            </div>
          ) : (
            <div
              key={index}
              onClick={() => onSelect(index)}
              className={`rounded-lg border bg-white px-5 py-4 ${
                selected === index ? "border-blue-300 ring-1 ring-blue-200" : "border-slate-200"
              }`}
            >
              <Steps steps={message.steps} done={message.done} />
              {message.error && <p className="text-sm text-red-600">{message.error}</p>}
              {message.text && (
                <Answer text={message.text} sources={message.sources} onOpenSource={onOpenSource} />
              )}
            </div>
          ),
        )}
        <div ref={bottom} />
      </div>

      <form
        className="flex gap-2 border-t border-slate-200 bg-white p-4"
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask a question about the specs..."
          className="flex-1 rounded-lg border border-slate-300 px-4 py-2 text-sm outline-none focus:border-blue-500"
        />
        <button
          disabled={busy || !input.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </div>
  );
}

// While the agents work, every tool call shows up as a line. Afterwards the steps fold
// into a one-line summary that can be opened again.
function Steps({ steps, done }: { steps: Step[]; done: boolean }) {
  if (!done) {
    return (
      <ul className="mb-2 space-y-1 text-xs text-slate-500">
        {steps.map((step, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className={i === steps.length - 1 ? "animate-pulse text-blue-600" : "text-emerald-600"}>●</span>
            {step.label}
          </li>
        ))}
        {steps.length === 0 && <li className="animate-pulse">Thinking...</li>}
      </ul>
    );
  }
  if (steps.length === 0) return null;
  return (
    <details className="mb-2 text-xs text-slate-500">
      <summary className="cursor-pointer select-none">{steps.length} steps</summary>
      <ul className="mt-1 space-y-1 pl-4">
        {steps.map((step, i) => (
          <li key={i}>
            <span className="text-slate-400">{step.agent}:</span> {step.label}
          </li>
        ))}
      </ul>
    </details>
  );
}
