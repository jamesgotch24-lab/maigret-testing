from io import BytesIO

import pytest
from pypdf import PdfReader
from fastapi.testclient import TestClient
from sqlmodel import select

import main
from main import Search, Session, engine
from maigret.report import generate_report_context


@pytest.fixture
def client():
    return TestClient(main.app)


def test_dashboard_index_and_static_assets_are_served(client):
    root = client.get("/")
    assert root.status_code == 200
    assert "Investigation overview" in root.text

    css = client.get("/static2/styles.css")
    assert css.status_code == 200
    assert "app-shell" in css.text


def test_investigation_lifecycle_and_pdf_report_output(client):
    create_resp = client.post("/api/investigations", json={"title": "Case A"})
    assert create_resp.status_code == 201
    investigation_id = create_resp.json()["id"]

    search_resp = client.post(
        "/api/search",
        json={
            "username": "alice",
            "investigation_id": investigation_id,
            "timeout": 5,
            "top_sites": 50,
            "report_format": "pdf",
        },
    )
    assert search_resp.status_code == 202
    search_id = search_resp.json()["id"]

    with Session(engine) as session:
        session.add(
            main.Result(
                search_id=search_id,
                site_name="example",
                username="alice",
                status="Claimed",
                status_text="Claimed",
                url="https://example.com/alice",
                url_main="https://example.com",
                tags_json='["social"]',
                profile_json='{"name": "Alice"}',
            )
        )
        session.commit()

    pdf_resp = client.get(f"/api/searches/{search_id}/report?format=pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"].startswith("application/pdf")

    delete_resp = client.delete(f"/api/investigations/{investigation_id}")
    assert delete_resp.status_code == 204


def test_pdf_report_contains_every_saved_claimed_site(client):
    investigation = client.post(
        "/api/investigations", json={"title": "Complete PDF case"}
    ).json()
    search = client.post(
        "/api/search",
        json={
            "username": "pdfverify",
            "investigation_id": investigation["id"],
            "top_sites": 1,
        },
    ).json()

    with Session(engine) as session:
        session.add_all(
            [
                main.Result(
                    search_id=search["id"],
                    site_name="first-site",
                    username="pdfverify",
                    status="Claimed",
                    status_text="Claimed",
                    url="https://first.example/pdfverify",
                    url_main="https://first.example",
                    profile_json='{"name": "First"}',
                ),
                main.Result(
                    search_id=search["id"],
                    site_name="second-site",
                    username="pdfverify",
                    status="Claimed",
                    status_text="Claimed",
                    url="https://second.example/pdfverify",
                    url_main="https://second.example",
                    profile_json='{"location": "Second"}',
                ),
            ]
        )
        session.commit()

    response = client.get(f"/api/searches/{search['id']}/report?format=pdf")
    assert response.status_code == 200
    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages
    )
    assert "first-site" in text
    assert "second-site" in text
    assert "https://first.example/pdfverify" in text
    assert "https://second.example/pdfverify" in text


def test_generate_report_context_keeps_claimed_results_visible_for_pdf():
    result_map = {
        "example": {
            "status": type(
                "StatusLike",
                (),
                {
                    "status": "Claimed",
                    "ids_data": {"name": "Alice"},
                    "tags": ["social"],
                    "error": None,
                    "context": "Claimed",
                },
            )(),
            "url_user": "https://example.com/alice",
            "url_main": "https://example.com",
            "http_status": 200,
            "is_similar": False,
        }
    }

    context = generate_report_context([("alice", "username", result_map)])
    assert context["results"][0][2]["example"]["found"] is True


def test_run_maigret_handles_search_failures_without_partial_nameerror(monkeypatch):
    class DummySettings:
        def load(self):
            return None

    class DummyDatabase:
        def load_from_path(self, _path):
            return self

        def ranked_sites_dict(self, **kwargs):
            return {"example": object()}

    def fake_search(*args, **kwargs):
        raise RuntimeError("search exploded")

    with Session(engine) as session:
        investigation = main.Investigation(
            title="Regression case", primary_username="alice"
        )
        session.add(investigation)
        session.commit()
        session.refresh(investigation)
        search = Search(
            investigation_id=investigation.id, username="alice", options_json="{}"
        )
        session.add(search)
        session.commit()
        session.refresh(search)
        search_id = search.id

    monkeypatch.setattr(main, "Settings", DummySettings)
    monkeypatch.setattr(main, "MaigretDatabase", DummyDatabase)
    monkeypatch.setattr(main, "build_cloudflare_bypass_config", lambda _settings: {})
    monkeypatch.setattr(main.maigret, "search", fake_search)

    main.run_maigret(
        search_id,
        "alice",
        {
            "all_sites": False,
            "top_sites": 1,
            "timeout": 5,
            "extract": False,
            "recursive": False,
            "check_domains": False,
            "tags": [],
            "excluded_tags": [],
            "site_list": [],
            "keywords": [],
        },
    )

    with Session(engine) as session:
        updated = session.get(Search, search_id)
        assert updated is not None
        assert updated.status == "failed"
        assert "search exploded" in updated.error_message


def test_startup_cleanup_removes_demo_alice_records():
    with Session(engine) as session:
        investigation = main.Investigation(title="Alice demo", primary_username="alice")
        session.add(investigation)
        session.commit()
        session.refresh(investigation)
        session.add(
            Search(
                investigation_id=investigation.id, username="alice", options_json="{}"
            )
        )
        session.commit()

    main.cleanup_demo_records()

    with Session(engine) as session:
        assert (
            session.exec(
                select(main.Investigation).where(
                    main.Investigation.primary_username == "alice"
                )
            ).all()
            == []
        )
        assert (
            session.exec(select(Search).where(Search.username == "alice")).all() == []
        )


def test_graph_is_built_as_a_connected_mindmap(client):
    create_resp = client.post("/api/investigations", json={"title": "Mindmap case"})
    assert create_resp.status_code == 201
    investigation_id = create_resp.json()["id"]

    search_resp = client.post(
        "/api/search",
        json={
            "username": "alice",
            "investigation_id": investigation_id,
            "timeout": 5,
            "top_sites": 10,
            "report_format": "json",
        },
    )
    assert search_resp.status_code == 202
    search_id = search_resp.json()["id"]

    with Session(engine) as session:
        result = main.Result(
            search_id=search_id,
            site_name="example",
            username="alice",
            status="Claimed",
            status_text="Claimed",
            url="https://example.com/alice",
            url_main="https://example.com",
            tags_json='["social"]',
            profile_json='{"name": "Alice"}',
        )
        session.add(result)
        session.commit()
        session.refresh(result)
        session.add(
            main.DiscoveredIdentity(
                search_id=search_id,
                identifier="alice-social",
                identifier_type="username",
                source_site="example",
            )
        )
        session.commit()

    graph = client.get("/api/graph").json()
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = [(edge["source"], edge["target"]) for edge in graph["edges"]]
    result_node_id = next(
        node_id
        for node_id in nodes
        if node_id.startswith("result:")
        and nodes[node_id].get("source_url") == "https://example.com/alice"
    )
    identity_node_id = next(
        node_id
        for node_id in nodes
        if node_id.startswith("identity:")
        and nodes[node_id].get("source_url") == "https://example.com/alice"
    )

    assert f"investigation:{investigation_id}" in nodes
    assert f"search:{search_id}" in nodes
    assert nodes[result_node_id]["source_url"] == "https://example.com/alice"
    assert nodes[identity_node_id]["source_url"] == "https://example.com/alice"
    assert (f"investigation:{investigation_id}", f"search:{search_id}") in edges
    assert (f"search:{search_id}", result_node_id) in edges
    assert any(
        source == result_node_id and target.startswith("identity:")
        for source, target in edges
    )

    delete_resp = client.delete(f"/api/investigations/{investigation_id}")
    assert delete_resp.status_code == 204


def test_run_maigret_in_subprocess_starts_worker(monkeypatch):
    captured = {}

    class DummyPopen:
        def __init__(
            self, args, env=None, stdout=None, stderr=None, start_new_session=None
        ):
            captured["args"] = args
            captured["env"] = env
            captured["stdout"] = stdout
            captured["stderr"] = stderr
            captured["start_new_session"] = start_new_session

    monkeypatch.setattr(main.subprocess, "Popen", DummyPopen)
    monkeypatch.setattr(main.sys, "executable", "/tmp/python")

    main.run_maigret_in_subprocess(42, "alice", {"top_sites": 5})

    assert captured["args"][0] == "/tmp/python"
    assert captured["args"][1].endswith("main.py")
    assert captured["env"]["MAIGRET_DASHBOARD_SEARCH_ID"] == "42"
    assert captured["env"]["MAIGRET_DASHBOARD_USERNAME"] == "alice"
    assert captured["env"]["MAIGRET_DASHBOARD_CHILD"] == "1"


def test_terminal_endpoint_runs_maigret_help_command(client):
    response = client.post(
        "/api/terminal/execute", json={"command": "python -m maigret --help"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["exit_code"] == 0
    assert "usage:" in payload["output"].lower()
