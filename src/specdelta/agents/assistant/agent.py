"""SpecDelta agents.

coordinator (root_agent)
  `-- search_agent   answers questions from the spec text, with citations (F1, F4, F5)

The search agent is a single_turn sub-agent: ADK attaches it to the coordinator as a
tool, so its answer comes back to the coordinator instead of taking over the chat. The
diff and table agents (M4) are added the same way.
"""

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.genai import types

from specdelta import config
from specdelta.tools.spec_tools import (
    get_clause,
    get_table,
    lookup_term,
    search_specs,
    search_table_rows,
)

SEARCH_INSTRUCTION = """You answer questions about 3GPP specifications using only the
text you get from your tools. The corpus holds TS 38.300 (NR overall description),
TS 38.321 (MAC), TS 38.101-1 (UE RF requirements, FR1) for Rel-17 and Rel-18, and the
vocabulary TR 21.905.

Never answer from your own knowledge of 3GPP, it may belong to another release or spec.
Always call search_specs first, even if you think you know the answer.

How to work:
- Start with search_specs. Pass specs or releases only if the question names them.
  Without a release, the latest release is searched, which is what users usually want.
- If a result is cut off or you need the surrounding text, call get_clause.
- Clauses often point to other clauses ("see clause 5.2"). Follow such references with
  get_clause when they are needed to answer the question.
- For table results with full_table false, use search_table_rows to find the rows you
  need (for example a band like "n78" or a CA configuration), or get_table.
- For abbreviations and defined terms, use lookup_term. Pass the spec the user is asking
  about, because abbreviations can mean different things in different specs.

How to answer:
- Every statement must be backed by a citation exactly as given by the tools, for
  example [38.300 Rel-18 §15.4.2.3]. Put it right after the statement it supports.
- Only cite clauses you actually got from a tool in this conversation.
- If the tools do not return enough to answer, say so plainly instead of guessing.
  Point out when a topic is specified in a spec that is not in the corpus, if the text
  says so (for example "see TS 38.331").
- Be concise and precise. Keep numbers, units and conditions exactly as in the spec.
- When the answer is in a table, reproduce the relevant rows and columns as a Markdown
  table with the caption, instead of picking single values. Do not leave out rows that
  match the question (for example all modulations of a waveform).
"""

COORDINATOR_INSTRUCTION = """You are the entry point of SpecDelta, an assistant for 3GPP
specifications (TS 38.300, TS 38.321, TS 38.101-1 in Rel-17 and Rel-18, TR 21.905).

For any question about the content of these specs, call search_agent with the user's
question, including any spec or release the user mentioned. Then give the user the
answer of search_agent. Keep all its citations ([spec release §clause]) exactly as they
are and do not add facts of your own.

For greetings or questions about what you can do, answer briefly yourself.
"""

# Retry with backoff, Vertex AI answers with 429 when the shared quota is busy. Kept
# short (about 30 s at most), longer silent waiting looks like a hang in the UI.
FLASH = Gemini(
    model=config.FLASH_MODEL,
    retry_options=types.HttpRetryOptions(attempts=4, initial_delay=2, max_delay=15),
)

# No thinking: with it, one answer took 15-40 s instead of 4-6 s. The agents mostly
# route and write up tool results, the eval shows whether that costs answer quality.
NO_THINKING = types.ThinkingConfig(thinking_budget=0)

search_agent = Agent(
    name="search_agent",
    model=FLASH,
    description="Answers questions about the content of the 3GPP specs, with clause citations.",
    instruction=SEARCH_INSTRUCTION,
    tools=[search_specs, get_clause, get_table, search_table_rows, lookup_term],
    generate_content_config=types.GenerateContentConfig(temperature=0, thinking_config=NO_THINKING),
    mode="single_turn",
)

root_agent = Agent(
    name="coordinator",
    model=FLASH,
    description="Routes questions about 3GPP specs to the right specialist agent.",
    instruction=COORDINATOR_INSTRUCTION,
    generate_content_config=types.GenerateContentConfig(thinking_config=NO_THINKING),
    sub_agents=[search_agent],
)
