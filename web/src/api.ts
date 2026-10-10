import type { Clause, Filters, Source, Step, Table } from "./types";

export type ChatEvent =
  | { type: "session"; session_id: string }
  | ({ type: "step" } & Step)
  | { type: "sources"; sources: Source[] }
  | { type: "answer"; text: string }
  | { type: "error"; message: string };

// POST /api/chat answers with server-sent events. EventSource only supports GET, so the
// stream is read by hand: events are "data: {...}" blocks separated by a blank line.
export async function streamChat(
  message: string,
  sessionId: string | null,
  filters: Filters,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      // An empty selection means "no restriction", so it is sent as null
      specs: filters.specs.length ? filters.specs : null,
      releases: filters.releases.length ? filters.releases : null,
    }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? ""; // the last block may still be incomplete
    for (const block of blocks) {
      if (block.startsWith("data: ")) onEvent(JSON.parse(block.slice(6)));
    }
  }
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

export function fetchAvailable(): Promise<{ specs: Record<string, string[]> }> {
  return getJson("/api/filters");
}

export function fetchClause(spec: string, release: string, clauseId: string): Promise<Clause> {
  const query = new URLSearchParams({ spec, release, clause_id: clauseId });
  return getJson(`/api/clause?${query}`);
}

export function fetchTable(spec: string, release: string, tableId: string): Promise<Table> {
  const query = new URLSearchParams({ spec, release, table_id: tableId });
  return getJson(`/api/table?${query}`);
}
