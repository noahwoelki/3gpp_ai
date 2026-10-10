"""Rerank search candidates with the Vertex AI ranking API (Discovery Engine).

Called over REST with the default Google credentials, so no extra client library is
needed. Records longer than the model limit (1024 tokens) are truncated by the API.
"""

import google.auth
from google.auth.transport.requests import AuthorizedSession

from specdelta import config

MODEL = "semantic-ranker-default-004"

_session: AuthorizedSession | None = None


def session() -> AuthorizedSession:
    global _session
    if _session is None:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        _session = AuthorizedSession(credentials)
    return _session


def rerank(query: str, records: list[tuple[str, str, str]]) -> dict[str, float]:
    """Relevance score (0..1) per record id. Records are (id, title, content)."""
    url = (
        f"https://discoveryengine.googleapis.com/v1/projects/{config.PROJECT_ID}"
        "/locations/global/rankingConfigs/default_ranking_config:rank"
    )
    body = {
        "model": MODEL,
        "query": query,
        "topN": len(records),
        "records": [{"id": i, "title": title, "content": content} for i, title, content in records],
    }
    response = session().post(url, json=body, headers={"X-Goog-User-Project": config.PROJECT_ID})
    response.raise_for_status()
    return {record["id"]: record.get("score", 0.0) for record in response.json().get("records", [])}
