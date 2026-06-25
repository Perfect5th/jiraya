"""Production ``TicketSource`` backed by the Jira Cloud REST API.

Implements the same port as the in-memory fake. The ``httpx.Client`` is
injectable so the adapter can be exercised with ``httpx.MockTransport`` without
a live Jira instance.
"""

from __future__ import annotations

from typing import Any

import httpx

from ...domain import Priority, Ticket, TicketStatus
from ...ports import TicketSource

_DEFAULT_JQL = 'status in ("To Do", "Untriaged") ORDER BY created ASC'
_FIELDS = "summary,description,reporter,priority,status,labels,created,updated"

_PRIORITY_BY_NAME = {p.value.lower(): p for p in Priority}
_STATUS_BY_NAME = {s.value.lower(): s for s in TicketStatus}


class JiraRestTicketSource(TicketSource):
    """Reads and transitions issues via Jira's REST API (v3)."""

    def __init__(
        self,
        *,
        base_url: str,
        email: str | None = None,
        api_token: str | None = None,
        jql: str = _DEFAULT_JQL,
        max_results: int = 50,
        client: httpx.Client | None = None,
    ) -> None:
        self._jql = jql
        self._max_results = max_results
        auth = httpx.BasicAuth(email, api_token) if email and api_token else None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

    def fetch_untriaged(self) -> list[Ticket]:
        resp = self._client.get(
            "/rest/api/3/search",
            params={
                "jql": self._jql,
                "fields": _FIELDS,
                "maxResults": self._max_results,
            },
        )
        resp.raise_for_status()
        issues = resp.json().get("issues", [])
        return [self._issue_to_ticket(issue) for issue in issues]

    def get(self, key: str) -> Ticket | None:
        resp = self._client.get(
            f"/rest/api/3/issue/{key}", params={"fields": _FIELDS}
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._issue_to_ticket(resp.json())

    def transition(self, key: str, status: TicketStatus) -> Ticket:
        transition_id = self._find_transition_id(key, status)
        if transition_id is None:
            raise ValueError(
                f"No Jira transition to '{status}' available for {key}"
            )
        resp = self._client.post(
            f"/rest/api/3/issue/{key}/transitions",
            json={"transition": {"id": transition_id}},
        )
        resp.raise_for_status()
        updated = self.get(key)
        if updated is None:
            raise KeyError(f"Ticket {key} disappeared after transition")
        return updated

    # -- helpers --------------------------------------------------------------

    def _find_transition_id(self, key: str, status: TicketStatus) -> str | None:
        resp = self._client.get(f"/rest/api/3/issue/{key}/transitions")
        resp.raise_for_status()
        target = status.value.lower()
        for transition in resp.json().get("transitions", []):
            to_name = transition.get("to", {}).get("name", "").lower()
            if to_name == target or transition.get("name", "").lower() == target:
                return str(transition.get("id"))
        return None

    def _issue_to_ticket(self, issue: dict[str, Any]) -> Ticket:
        fields = issue.get("fields", {})
        priority_name = (fields.get("priority") or {}).get("name", "")
        status_name = (fields.get("status") or {}).get("name", "")
        reporter = (fields.get("reporter") or {}).get("displayName", "unknown")
        return Ticket(
            key=issue.get("key", "UNKNOWN"),
            project=str(issue.get("key", "UNKNOWN-0")).split("-", 1)[0],
            summary=fields.get("summary", ""),
            description=_render_description(fields.get("description")),
            reporter=reporter,
            priority=_PRIORITY_BY_NAME.get(priority_name.lower(), Priority.MEDIUM),
            status=_STATUS_BY_NAME.get(status_name.lower(), TicketStatus.TODO),
            labels=tuple(fields.get("labels", []) or ()),
        )

    def close(self) -> None:
        self._client.close()


def _render_description(value: Any) -> str:
    """Render a Jira description (plain string or ADF document) as text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):  # Atlassian Document Format
        return _adf_to_text(value).strip()
    return str(value)


def _adf_to_text(node: Any) -> str:
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        parts = [_adf_to_text(child) for child in node.get("content", [])]
        text = "".join(parts)
        if node.get("type") in {"paragraph", "heading"}:
            return text + "\n"
        return text
    if isinstance(node, list):
        return "".join(_adf_to_text(child) for child in node)
    return ""
