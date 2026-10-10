// Shapes of the data coming from the API (src/specdelta/api.py)

export type Source = {
  tool: string;
  citation: string; // "[38.300 Rel-18 §15.4.2.3]"
  spec: string;
  release: string;
  clause_id: string;
  title: string;
  kind: "text" | "table" | "table_description" | "glossary";
  table_id: string | null;
  content: string;
  path?: string;
  found_by?: "vector" | "keyword" | "both";
  rerank_score?: number;
  full_table?: boolean | null;
  block_start?: number | null;
  block_end?: number | null;
  row_start?: number | null;
  row_end?: number | null;
};

export type Step = { agent: string; tool: string; label: string };

export type ChatMessage =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      text: string; // empty while the answer is being generated
      steps: Step[];
      sources: Source[];
      error?: string;
      done: boolean;
    };

export type Filters = { specs: string[]; releases: string[] };

export type Block =
  | { type: "paragraph"; style: string; text: string }
  | {
      type: "table";
      table_id: string;
      caption: string;
      header_rows: number;
      rows: string[][];
    };

export type Clause = {
  spec: string;
  release: string;
  clause_id: string;
  title: string;
  path: string[];
  blocks: Block[];
};

export type Table = {
  spec: string;
  release: string;
  clause_id: string;
  table_id: string;
  caption: string;
  header_rows: number;
  rows: string[][];
};
