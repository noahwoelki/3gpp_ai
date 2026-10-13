"""FastAPI app: the agent API at /api and the React UI at /.

POST /api/chat streams server-sent events while the agents work:

    {"type": "session", "session_id": "..."}
    {"type": "step", "agent": "search_agent", "tool": "search_specs", "label": "Searching ..."}
    {"type": "sources", "sources": [...]}      passages the tools returned
    {"type": "answer", "text": "..."}           final answer with citations
    {"type": "error", "message": "..."}

GET /api/filters, /api/clause and /api/table serve the filter choices and the full
clause or table behind a source, for the source viewer.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field

from specdelta import config
from specdelta.agents.assistant.agent import root_agent
from specdelta.tools import spec_tools

APP_NAME = "specdelta"
ANSWER_TIMEOUT_SECONDS = 90
# What ADK hands to the coordinator when a sub-agent fails, e.g. after a 429 from Gemini
SUB_AGENT_ERROR = "Error running sub-agent"
BUSY_MESSAGE = "The model service is busy right now. Please try again in a moment."
SPECIALISTS = {agent.name for agent in root_agent.sub_agents}
# Hard cap on model calls per question, so an agent that keeps calling tools without
# getting anywhere stops instead of running into the time limit
RUN_CONFIG = RunConfig(max_llm_calls=15)

# The stream stops as soon as the answer is there, which ends the ADK run early.
# OpenTelemetry then logs a harmless "Failed to detach context" traceback every time.
logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
USER_ID = "web"
WEB_DIST = config.REPO_ROOT / "web" / "dist"

runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading the chunks and building the BM25 index takes a few seconds, do it at
    # startup instead of in the first request
    await asyncio.to_thread(spec_tools.searcher)
    yield


app = FastAPI(title="SpecDelta", lifespan=lifespan)


# The service is public, so very long inputs are refused instead of being sent to Gemini
MAX_MESSAGE_CHARS = 2000


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    session_id: str | None = None
    specs: list[str] | None = None
    releases: list[str] | None = None


def step_label(tool: str, args: dict) -> str:
    """Short human readable description of a tool call for the progress display."""
    where = " ".join(
        filter(None, [", ".join(args.get("specs") or []), ", ".join(args.get("releases") or [])])
    )
    labels = {
        "search_agent": "Asking the search agent",
        "search_specs": f'Searching {where or "the specs"} for "{args.get("query", "")}"',
        "get_clause": f"Reading {args.get('spec')} {args.get('release')} §{args.get('clause_id')}",
        "get_table": f"Reading table {args.get('table_id')} of {args.get('spec')}",
        "search_table_rows": f'Looking for "{args.get("text")}" in table {args.get("table_id")}',
        "lookup_term": f'Looking up "{args.get("term")}"',
    }
    return labels.get(tool, f"Calling {tool}")


def sources_from(tool: str, args: dict, response: dict) -> list[dict]:
    """Turn a tool result into source entries for the sources panel."""
    if "error" in response:
        return []
    if tool == "search_specs":
        return [dict(r, tool=tool) for r in response.get("results", [])]
    if tool in ("get_clause", "get_table", "search_table_rows"):
        return [
            {
                "tool": tool,
                "citation": response["citation"],
                "spec": args.get("spec"),
                "release": args.get("release"),
                "clause_id": response["citation"].split("§")[-1].rstrip("]"),
                "title": response.get("title") or response.get("caption", ""),
                "kind": "text" if tool == "get_clause" else "table",
                "table_id": args.get("table_id"),
                "content": response.get("text")
                or response.get("table")
                or response.get("rows", ""),
            }
        ]
    if tool == "lookup_term":
        return [
            {
                "tool": tool,
                "citation": entry["citation"],
                "spec": entry["spec"],
                "release": entry["release"],
                "clause_id": entry["clause_id"],
                "title": f"{entry['term']} ({entry['kind']})",
                "kind": "glossary",
                "table_id": None,
                "content": entry["text"],
            }
            for entry in response.get("entries", [])
        ]
    return []


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def chat_events(request: ChatRequest):
    session_id = request.session_id
    session = None
    if session_id:
        session = await runner.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
    if session is None:
        session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    yield sse({"type": "session", "session_id": session.id})

    message = types.Content(role="user", parts=[types.Part(text=request.message)])
    filters = {"specs": request.specs, "releases": request.releases}
    calls: dict[str, tuple[str, dict]] = {}  # function call id -> (tool, args)
    try:
        async with asyncio.timeout(ANSWER_TIMEOUT_SECONDS):
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=message,
                state_delta={"ui_filters": filters},
                run_config=RUN_CONFIG,
            ):
                for part in event.content.parts if event.content and event.content.parts else []:
                    if part.function_call:
                        call = part.function_call
                        args = dict(call.args or {})
                        calls[call.id] = (call.name, args)
                        yield sse(
                            {
                                "type": "step",
                                "agent": event.author,
                                "tool": call.name,
                                "label": step_label(call.name, args),
                            }
                        )
                    elif part.function_response:
                        result = part.function_response
                        response = dict(result.response or {})
                        # Stop here instead of letting the coordinator explain the failure
                        # in its own words, which tends to produce made-up reasons
                        if str(response.get("result", "")).startswith(SUB_AGENT_ERROR):
                            yield sse({"type": "error", "message": BUSY_MESSAGE})
                            return
                        # The answer of a specialist agent goes to the user as it is.
                        # Letting the coordinator repeat it costs a model call and it
                        # tends to drop citations on the way.
                        if result.name in SPECIALISTS and response.get("result"):
                            yield sse({"type": "answer", "text": response["result"]})
                            return
                        tool, args = calls.get(result.id, (result.name, {}))
                        sources = sources_from(tool, args, response)
                        if sources:
                            yield sse({"type": "sources", "sources": sources})
                if event.author == root_agent.name and event.is_final_response() and event.content:
                    text = "".join(p.text or "" for p in event.content.parts or [])
                    if text:
                        yield sse({"type": "answer", "text": text})
    except TimeoutError:
        yield sse(
            {
                "type": "error",
                "message": f"No answer after {ANSWER_TIMEOUT_SECONDS} s. {BUSY_MESSAGE}",
            }
        )
    except Exception as error:  # report to the UI instead of breaking the stream
        yield sse({"type": "error", "message": str(error)})


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(chat_events(request), media_type="text/event-stream")


@app.get("/api/filters")
def filters() -> dict:
    """Specs and releases in the corpus, e.g. {"38.300": ["Rel-17", "Rel-18"]}."""
    return {"specs": spec_tools.searcher().available}


@app.get("/api/clause")
def clause(spec: str, release: str, clause_id: str) -> dict:
    row = spec_tools.query_one(
        f"""SELECT title, path, blocks FROM `{config.PROJECT_ID}.{config.BQ_DATASET}.clauses`
            WHERE spec = @spec AND release = @release AND clause_id = @clause_id""",
        spec=spec,
        release=release,
        clause_id=clause_id,
    )
    if row is None:
        raise HTTPException(404, f"Clause {clause_id} not found in {spec} {release}")
    return {
        "spec": spec,
        "release": release,
        "clause_id": clause_id,
        "title": row["title"],
        "path": row["path"],
        "blocks": json.loads(row["blocks"]),
    }


@app.get("/api/table")
def table(spec: str, release: str, table_id: str) -> dict:
    row = spec_tools.load_table(spec, release, table_id)
    if row is None:
        raise HTTPException(404, f"Table {table_id} not found in {spec} {release}")
    return {
        "spec": spec,
        "release": release,
        "clause_id": row["clause_id"],
        "table_id": table_id,
        "caption": row["caption"],
        "header_rows": row["header_rows"],
        "rows": json.loads(row["table_rows"]),
    }


# The built React app, if there is one (npm run build in web/). Mounted last so the
# /api routes take precedence.
if Path(WEB_DIST).exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
