from __future__ import annotations

import json

import httpx
import pytest

from jiraya.adapters.jira import JiraRestTicketSource
from jiraya.domain import Priority, TicketStatus

_ADF = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "paragraph",
         "content": [{"type": "text", "text": "Steps to reproduce the bug."}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "Second line."}]},
    ],
}


def _issue(status_name: str = "To Do"):
    return {
        "key": "PROJ-1",
        "fields": {
            "summary": "Login fails",
            "description": _ADF,
            "reporter": {"displayName": "Alice"},
            "priority": {"name": "High"},
            "status": {"name": status_name},
            "labels": ["bug"],
        },
    }


def _make_client(state: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/rest/api/3/search":
            return httpx.Response(200, json={"issues": [_issue(state["status"])]})
        if path == "/rest/api/3/issue/PROJ-1/transitions":
            if request.method == "GET":
                return httpx.Response(200, json={"transitions": [
                    {"id": "31", "name": "Start work", "to": {"name": "In Progress"}},
                ]})
            body = json.loads(request.content)
            assert body["transition"]["id"] == "31"
            state["status"] = "In Progress"
            return httpx.Response(204)
        if path == "/rest/api/3/issue/PROJ-1":
            return httpx.Response(200, json=_issue(state["status"]))
        if path == "/rest/api/3/issue/MISSING":
            return httpx.Response(404, json={"errorMessages": ["not found"]})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler),
                        base_url="https://example.atlassian.net")


def test_fetch_untriaged_maps_issue_and_renders_adf():
    src = JiraRestTicketSource(base_url="https://x", client=_make_client({"status": "To Do"}))
    tickets = src.fetch_untriaged()
    assert len(tickets) == 1
    t = tickets[0]
    assert t.key == "PROJ-1"
    assert t.project == "PROJ"
    assert t.reporter == "Alice"
    assert t.priority is Priority.HIGH
    assert t.status is TicketStatus.TODO
    assert t.labels == ("bug",)
    assert "Steps to reproduce the bug." in t.description
    assert "Second line." in t.description


def test_transition_finds_and_applies_transition():
    src = JiraRestTicketSource(base_url="https://x", client=_make_client({"status": "To Do"}))
    updated = src.transition("PROJ-1", TicketStatus.IN_PROGRESS)
    assert updated.status is TicketStatus.IN_PROGRESS


def test_transition_without_match_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/transitions"):
            return httpx.Response(200, json={"transitions": []})
        return httpx.Response(200, json=_issue())

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://x")
    src = JiraRestTicketSource(base_url="https://x", client=client)
    with pytest.raises(ValueError):
        src.transition("PROJ-1", TicketStatus.DONE)


def test_get_returns_none_on_404():
    src = JiraRestTicketSource(base_url="https://x", client=_make_client({"status": "To Do"}))
    assert src.get("MISSING") is None
