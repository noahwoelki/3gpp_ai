"""Embed all searchable chunks with the Vertex AI embedding model.

Each chunk is embedded as its header plus content ("[38.300 Rel-18 §16.4.2 Title]\n...").
Row chunks of large tables (embed=False) are skipped, their table description is
embedded instead.

The model takes one text per request, so requests run in a thread pool. Vectors are
appended to data/embeddings/<spec>_<release>.jsonl as they arrive. Chunks that already
have a vector are skipped, so an interrupted or partly failed run can simply be restarted.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types

from specdelta import config
from specdelta.ingest.chunk import load_chunks
from specdelta.ingest.parse_docx import doc_info

WORKERS = 8


def embedding_text(chunk: dict) -> str:
    return f"{chunk['header']}\n{chunk['content']}"


def make_client() -> genai.Client:
    # Retry with backoff, mainly for 429 when we hit the per-minute quota
    retry = types.HttpRetryOptions(attempts=6, initial_delay=2, max_delay=60)
    return genai.Client(
        vertexai=True,
        project=config.PROJECT_ID,
        location=config.VERTEX_LOCATION,
        http_options=types.HttpOptions(retry_options=retry),
    )


def embed(client: genai.Client, text: str, task_type: str) -> list[float]:
    response = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type, output_dimensionality=config.EMBEDDING_DIMENSIONS
        ),
    )
    return response.embeddings[0].values


def load_embeddings(spec: str, release: str) -> dict[str, list[float]]:
    path = config.EMBEDDINGS_DIR / f"{spec}_{release}.jsonl"
    if not path.exists():
        return {}
    with path.open() as f:
        return {row["chunk_id"]: row["embedding"] for row in map(json.loads, f)}


def main() -> None:
    config.EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    client = make_client()
    for name in config.DOCUMENTS:
        spec, release, _ = doc_info(name)
        done = load_embeddings(spec, release)
        todo = [c for c in load_chunks(spec, release) if c["embed"] and c["chunk_id"] not in done]
        print(f"{spec}_{release}: {len(done)} embedded, {len(todo)} to do")
        if not todo:
            continue

        failed = 0
        path = config.EMBEDDINGS_DIR / f"{spec}_{release}.jsonl"
        with path.open("a") as f, ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {
                pool.submit(embed, client, embedding_text(c), "RETRIEVAL_DOCUMENT"): c for c in todo
            }
            for count, future in enumerate(as_completed(futures), start=1):
                chunk = futures[future]
                try:
                    vector = future.result()
                except Exception as error:  # keep going, a rerun picks up what failed
                    failed += 1
                    print(f"  failed {chunk['chunk_id']}: {error}")
                    continue
                f.write(json.dumps({"chunk_id": chunk["chunk_id"], "embedding": vector}) + "\n")
                if count % 200 == 0:
                    print(f"  {count}/{len(todo)}")
        print(f"  done, {failed} failed")


if __name__ == "__main__":
    main()
