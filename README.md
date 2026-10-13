# SpecDelta

A side project to try out agents and retrieval on Google Cloud with a corpus I know
well. You can ask questions about a few 3GPP specs and get answers that cite the clause
each statement comes from, e.g. `[38.300 Rel-18 §15.4.2.3]`. Comparing what changed
between releases is the next thing I want to add.

## Background

3GPP writes the standards for mobile networks (LTE, 5G NR). They are published as long
Word documents, organized in numbered clauses, and a new release comes out every year
or two. Engineers spend a lot of time looking things up in them and figuring out what
changed from one release to the next.

To keep it small, the corpus is seven documents. TS 38.300 (NR overview), TS 38.321
(MAC) and TS 38.101-1 (UE radio requirements) in Rel-17 and Rel-18, plus the 3GPP
vocabulary TR 21.905.

Some things that make this corpus harder than average text:

- Large parts are tables, not prose. 38.101-1 alone has around 700 tables, some with
  more than 2000 rows of band combinations. A table row on its own means nothing
  without its header and notes.
- Questions are often about exact identifiers like `NS_05`, `n78` or `CA_n3A-n78A`.
  These look almost the same to an embedding model.
- The same abbreviation can mean different things in different specs. NCR is
  "Neighbour Cell Relation" in 38.300 and "Network-Controlled Repeater" in 38.321.
- The structure of the Word files is not fully consistent, e.g. a custom heading style
  in one release, footnote markers as superscripts glued to the values (band n24 with
  note 16 reads "n2416"), or typos in clause numbers.

## AI

**Parsing does most of the work.** Every clause is stored with its number, title and
content, and tables keep their structure (caption, header rows, cells, notes). Plain
text for search, formatted text for the UI, and the clause diff between releases are
all derived from that.

**Tables get special treatment.** Each table chunk repeats the header and carries only
the notes its rows refer to. Very large tables are not embedded row by row, because
hundreds of near-identical chunks would crowd out everything else. Instead Gemini
writes a short description of each, which is embedded, and the agent fetches the
actual rows when it needs them. When a table is found and fits into the context, the
whole table is passed to the model instead of a fragment.

**Search is hybrid.** Vector search alone failed on exactly the questions engineers
ask. For "What is the A-MPR for NS_05?" it returned 30 A-MPR clauses for other NS
values and none for NS_05. So keyword search (BM25, with a tokenizer that keeps
identifiers like `CA_n3A-n78A` intact) runs next to it, both lists are merged with
reciprocal rank fusion, and a reranker sorts the result.

**Agents.** A coordinator passes questions to a search agent built with Google ADK.
The search agent has a few tools (search, read a clause, read a table, find rows in a
table, look up a term) and is told to answer only from what they return. In one test
it skipped the tools and answered from memory with a made-up clause number, which is
why the UI marks every citation that does not match a retrieved source in red. A proper
check before the answer is shown is still on the list.

**Model choice.** Gemini 2.5 Flash for everything, with thinking turned off. With
thinking, an answer took 15 to 40 seconds instead of about 5, without a visible gain
for this kind of lookup.

## Cloud

Everything runs on Google Cloud.

- **Vertex AI** for Gemini, the embeddings (`gemini-embedding-001`) and the reranker.
- **BigQuery** stores clauses, chunks with their embeddings, all tables and the
  glossary. Vector search runs there with `VECTOR_SEARCH`. BigQuery's text search only
  says match or no match, so the keyword ranking runs in the app over the chunk texts,
  which are only a few MB.
- **Cloud Run** hosts one container with a FastAPI backend and a small React UI. The UI
  streams the agent steps while it works and shows the retrieved sources next to the
  answer. It scales to zero when nobody uses it.