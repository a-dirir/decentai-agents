import asyncio
from pathlib import Path

import pytest

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
    assert set(agents) == {"demo_agent", "file_desk", "web_reader"}
    assert all(agent.instance.missing_functions() == [] for agent in agents.values())


def test_demo_agent_json_round_trip_preserves_priority_and_content(agents):
    provider = InMemoryResourceProvider()
    executor = FunctionExecutor(provider=provider)

    async def scenario():
        await executor.invoke(agents["demo_agent"], "demo_agent.note.save", {
            "notebook": "Work", "title": "Handoff", "priority": 2,
            "content": {"body": "Call the customer", "done": False},
        })
        exported, status = await executor.invoke(
            agents["demo_agent"], "demo_agent.archive.export",
            {"notebook": "work", "format": "json"}, chat_level=2,
        )
        assert status == "success"
        assert exported["filename"] == "work-notes.json"

        imported, status = await executor.invoke(
            agents["demo_agent"], "demo_agent.archive.import",
            {"notebook": "copy", "file_ref": exported["file_ref"]},
            chat_level=2,
        )
        assert status == "success"
        copied = provider.data["demo_agent__note"][imported["note_refs"][0]]["keys"]
        assert copied["priority"] == 2
        assert copied["content"] == {"body": "Call the customer", "done": False}

    run(scenario())


def test_demo_agent_rejects_bad_import_before_creating_any_notes(agents):
    provider = InMemoryResourceProvider()
    executor = FunctionExecutor(provider=provider)

    async def scenario():
        uploaded = await provider.create_file(
            "demo_agent__document", "bad.csv",
            "title,notebook,priority,content\nGood,x,2,{}\nBad,x,nope,{}\n",
        )
        result, status = await executor.invoke(
            agents["demo_agent"], "demo_agent.archive.import",
            {"notebook": "copy", "file_ref": uploaded["resource_ref"]},
            chat_level=2,
        )
        assert status == "error"
        assert "Invalid priority" in result["error"]
        assert provider.data.get("demo_agent__note", {}) == {}

    run(scenario())


def test_demo_agent_uses_a_bound_secret_for_the_simulated_external_action(agents):
    provider = InMemoryResourceProvider(secrets={
        "demo_agent__connection": {
            "base_url": "https://demo.invalid",
            "api_token": "test-token",
        }
    })
    executor = FunctionExecutor(provider=provider)

    async def scenario():
        connected, status = await executor.invoke(
            agents["demo_agent"], "demo_agent.sync.status", {}
        )
        assert status == "success"
        assert connected == {
            "connected": True,
            "remote": "simulated://notebook",
        }

        await executor.invoke(agents["demo_agent"], "demo_agent.note.save", {
            "notebook": "Work",
            "title": "Secret-backed demo",
        })
        pushed, status = await executor.invoke(
            agents["demo_agent"],
            "demo_agent.sync.push",
            {"notebook": "work"},
            chat_level=3,
        )
        assert status == "success"
        assert pushed["pushed"] == 1
        assert len(pushed["digest"]) == 64

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


def test_web_reader_blocks_private_destinations(monkeypatch):
    from decentai_agents.web_reader.tools.web_tool import WebTool

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(ValueError, match="not public"):
        WebTool._validate_public_url("http://internal.example/")
