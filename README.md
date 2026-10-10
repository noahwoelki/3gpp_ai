# SpecDelta

SpecDelta answers questions about 3GPP specifications and cites the clause every
statement comes from, e.g. `[38.300 Rel-18 §15.4.2.3]`. It runs on Google Cloud
(Vertex AI, BigQuery, Cloud Run) with agents built on Google ADK.

The corpus is small on purpose: TS 38.300 (NR overall description), TS 38.321 (MAC) and
TS 38.101-1 (UE radio requirements, FR1), each in Rel-17 and Rel-18, plus the 3GPP
vocabulary TR 21.905.

**Status:** first version. Question answering with citations, a sources view and
release/spec filters work. Comparing releases (what changed between Rel-17 and Rel-18,
per clause) is the next step; the clause diff behind it is already done
(`make diff`).

## How it works

```
 3GPP .docx  ->  parse  ->  clauses, tables, glossary  ->  chunks  ->  embeddings
                                                                          |
                                                                       BigQuery
                                                                          |
 browser  ->  Cloud Run: FastAPI + React UI  ->  ADK agents  ->  tools (search, clause, table, glossary)
```

**Parsing.** The specs come as Word files. Heading styles give the clause numbers, so
every clause is stored with its number, title, parent path and content. The content is
kept as an ordered list of blocks (paragraphs with their 3GPP style, and tables with
caption, header rows and cells), so it can be shown as plain text for search and diff,
or rendered properly in the UI. Superscript footnote markers in tables are kept as
`(note 3)` instead of being glued to the value (band "n24" with note 16 would otherwise
read "n2416").

**Chunking.** Text is cut into chunks of about 450 words at paragraph boundaries. Tables
are chunked separately, and every table chunk can be read on its own: caption, header
rows, a group of rows, and only the notes those rows refer to.

Large tables (three or more chunks, such as the CA configuration lists with up to 2000
rows) are 9% of the 38.101-1 tables but almost 30% of its chunks, and their chunks look
nearly identical to an embedding model. They are not embedded row by row. Instead a
short Gemini call writes a description of each such table, and that description is
embedded. The row chunks are still used for keyword search, where exact strings like
`CA_n3A-n78A` match well.

**Search.** Hybrid search, then reranking:
1. Vector search in BigQuery (`VECTOR_SEARCH`, `gemini-embedding-001`, 768 dimensions).
2. BM25 keyword search in Python. BigQuery's `SEARCH` function only returns true/false,
   so the keyword ranking happens in the app over the chunk texts (a few MB, loaded at
   startup). The tokenizer keeps identifiers like `CA_n3A-n78A` whole and also adds
   their parts.
3. Reciprocal rank fusion of both lists, then the Vertex AI ranking API.
4. One hit per table. If a table fits 1500 words (95% of all tables), the whole table
   goes into the context, otherwise the best matching part.

Without a release filter, each spec is searched in its latest release.

Both retrievers are needed. For "What is the A-MPR for NS_05?", vector search returns
30 A-MPR clauses for other NS values (NS_31, NS_65, ...) and none for NS_05, because to
an embedding model these look the same. Keyword search finds the right clause first,
and the reranker puts it on top.

**Agents.** A coordinator agent passes questions to a search agent, which uses the
tools `search_specs`, `get_clause`, `get_table`, `search_table_rows` and `lookup_term`
and answers only from what they return. Gemini 2.5 Flash runs with thinking turned off:
with thinking, one answer took 15-40 seconds instead of 4-6.

**UI.** The answer streams in step by step ("Searching 38.321 for ...", "Reading table
6.2.3.4-2 ..."). Citations are clickable. A citation shows up in red if the cited clause
was not among the retrieved sources. The sources panel lists every retrieved passage
with how it was found (vector, keyword or both) and its rerank score, and opens the full
clause or table with the retrieved part highlighted.

## Running it locally

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js, the `gcloud` CLI
and a Google Cloud project with billing enabled. No API keys are used. Locally the code
uses your own login (`gcloud auth application-default login`).

```
cp .env.example .env          # set GOOGLE_CLOUD_PROJECT
make sync                     # Python dependencies
```

**Get the specs.** The 3GPP documents are not part of this repo. `make download` fetches
the versions listed in `src/specdelta/config.py` from the public 3GPP archive
(`https://www.3gpp.org/ftp/Specs/archive/`) into `data/raw/` and unzips them.

**Build the index:**

```
make parse      # clauses, chunks, typed tables, glossary -> data/parsed/ (about 1 min)
make describe   # Gemini descriptions of the large tables
make embed      # embeddings for all searchable chunks
make load       # load everything into BigQuery
```

Each step writes its results to `data/`, and `describe` and `embed` skip what is already
done, so rerunning them is cheap.

**Try it:**

```
make search Q="How does cell DTX/DRX work?"       # search only, shows how each hit was found
make ask Q="What is the A-MPR for NS_05?"         # agents in the terminal
make diff SPEC=38.300 CLAUSE=15.4                 # clause diff Rel-17 -> Rel-18
make dev-api                                      # API on http://localhost:8080
make dev-web                                      # UI on http://localhost:5173
make dev-agent                                    # ADK dev UI on http://localhost:8000
make test
```

## Deploying to Google Cloud

The app runs as one Cloud Run service: FastAPI serves the API at `/api` and the built
React app at `/`. It scales to zero when idle. The service runs as its own service
account that can only read BigQuery and call Gemini and the ranking API.

```
make setup-gcp    # once: enable APIs, create the service account and its roles
make deploy       # build with Cloud Build and deploy (a few minutes)
make logs         # follow the service logs
```

`make deploy` prints the service URL (`https://specdelta-....run.app`). The service is
public: anyone with the URL can use it. To keep costs bounded, at most two instances
run at a time and questions are limited to 2000 characters. A billing budget alert on
the project is a good idea on top.

## Repository layout

```
src/specdelta/
  ingest/     download, parse_docx, chunk, tables, glossary, describe_tables, embed, load_bigquery
  search/     bm25, hybrid (vector + keyword + fusion + rerank), rerank
  diff/       clause matching and diff between releases
  tools/      functions the agents call
  agents/     ADK agents (coordinator, search agent)
  api.py      FastAPI app, streams agent steps to the UI
web/          React UI (Vite, Tailwind)
tests/
```

## Limitations

- Seven documents only. Answers about topics specified elsewhere (e.g. TS 38.331 for
  RRC) can only say where to look.
- Figures are images in the specs. Only their captions are indexed.
- Some 38.101-1 headings are numbered inconsistently in the spec itself (e.g.
  `6.5.A.2.2`). They are kept as they are.
- The demo is public without login, so it relies on the instance limit and a budget
  alert to keep costs in check.
- The citation check is visual only so far (red citations). The next step is to check
  citations before the answer is shown and let the agent revise it.
