import asyncio
import json
from pathlib import Path

import pytest
import requests

from ai_runtime.agents_layer.executor import FunctionExecutor
from ai_runtime.agents_layer.loader import AgentLoader
from ai_runtime.agents_layer.resources import InMemoryResourceProvider


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def agents():
    loaded, errors = AgentLoader(ROOT).load_all()
    assert errors == {}
    return loaded


def run(awaitable):
    return asyncio.run(awaitable)


def test_all_catalog_agents_load_and_implement_their_manifest(agents):
    assert set(agents) == {"file_desk", "jira_ops", "notebook", "web_reader"}
    assert all(agent.instance.missing_functions() == [] for agent in agents.values())


def test_notebook_json_round_trip_preserves_priority_and_content(agents):
    provider = InMemoryResourceProvider()
    executor = FunctionExecutor(provider=provider)

    async def scenario():
        await executor.invoke(agents["notebook"], "notebook.note.save", {
            "notebook": "Work", "title": "Handoff", "priority": 2,
            "content": {"body": "Call the customer", "done": False},
        })
        exported, status = await executor.invoke(
            agents["notebook"], "notebook.archive.export",
            {"notebook": "work", "format": "json"}, chat_level=2,
        )
        assert status == "success"
        assert exported["filename"] == "work-notes.json"

        imported, status = await executor.invoke(
            agents["notebook"], "notebook.archive.import",
            {"notebook": "copy", "file_ref": exported["file_ref"]},
            chat_level=2,
        )
        assert status == "success"
        copied = provider.data["notebook__note"][imported["note_refs"][0]]["keys"]
        assert copied["priority"] == 2
        assert copied["content"] == {"body": "Call the customer", "done": False}

    run(scenario())


def test_notebook_rejects_bad_import_before_creating_any_notes(agents):
    provider = InMemoryResourceProvider()
    executor = FunctionExecutor(provider=provider)

    async def scenario():
        uploaded = await provider.create_file(
            "notebook__document", "bad.csv",
            "title,notebook,priority,content\nGood,x,2,{}\nBad,x,nope,{}\n",
        )
        result, status = await executor.invoke(
            agents["notebook"], "notebook.archive.import",
            {"notebook": "copy", "file_ref": uploaded["resource_ref"]},
            chat_level=2,
        )
        assert status == "error"
        assert "Invalid priority" in result["error"]
        assert provider.data.get("notebook__note", {}) == {}

    run(scenario())


def test_file_desk_rejects_a_filename_that_becomes_blank(agents):
    result, status = run(FunctionExecutor(
        provider=InMemoryResourceProvider()
    ).invoke(
        agents["file_desk"], "file_desk.file.save",
        {"filename": "   ", "text": "body"},
    ))
    assert status == "error"
    assert "blank" in result["error"]


def response(status, payload=None, headers=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {"Content-Type": "application/json"})
    result._content = json.dumps(payload or {}).encode("utf-8") if status != 204 else b""
    result.encoding = "utf-8"
    return result


def test_jira_ops_reads_queue_and_performs_only_the_requested_transition(
    agents, monkeypatch
):
    calls = []

    def request(_session, method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/search/jql"):
            return response(200, {"issues": [{
                "key": "OPS-7", "fields": {
                    "summary": "Investigate alarm",
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Incident"},
                    "priority": {"name": "High"},
                    "assignee": {"displayName": "Ahmed"},
                    "updated": "2026-08-21T10:00:00.000+0000",
                },
            }], "total": 1})
        if url.endswith("/OPS-7/transitions") and method == "GET":
            return response(200, {"transitions": [
                {"id": "31", "name": "Resolve", "to": {"name": "Resolved"}},
                {"id": "41", "name": "Wait", "to": {"name": "Waiting for customer"}},
            ]})
        if url.endswith("/OPS-7/transitions") and method == "POST":
            return response(204)
        raise AssertionError((method, url))

    monkeypatch.setattr(requests.Session, "request", request)
    provider = InMemoryResourceProvider(secrets={
        "jira_ops__connection": {
            "base_url": "https://example.atlassian.net",
            "email": "agent@example.com", "api_token": "token",
        }
    })
    executor = FunctionExecutor(provider=provider)

    async def scenario():
        queue, status = await executor.invoke(
            agents["jira_ops"], "jira_ops.queue.my_open", {}
        )
        assert status == "success"
        assert queue["issues"][0]["key"] == "OPS-7"

        moved, status = await executor.invoke(
            agents["jira_ops"], "jira_ops.issue.transition",
            {"issue_key": "ops-7", "target_status": "Resolved"},
            chat_level=3,
        )
        assert status == "success"
        assert moved["transitioned"] is True

    run(scenario())
    posts = [call for call in calls if call[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2]["json"] == {"transition": {"id": "31"}}


def test_web_reader_blocks_private_destinations(monkeypatch):
    from decentai_agents.web_reader.tools.web_tool import WebTool

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(ValueError, match="not public"):
        WebTool._validate_public_url("http://internal.example/")
