import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

import main
from main import Search, Session, engine


@pytest.fixture
def client():
    return TestClient(main.app)


def test_dashboard_index_and_static_assets_are_served(client):
    root = client.get('/')
    assert root.status_code == 200
    assert 'Investigation overview' in root.text

    css = client.get('/static2/styles.css')
    assert css.status_code == 200
    assert 'app-shell' in css.text


def test_investigation_lifecycle_and_pdf_report_output(client):
    create_resp = client.post('/api/investigations', json={'title': 'Case A'})
    assert create_resp.status_code == 201
    investigation_id = create_resp.json()['id']

    search_resp = client.post('/api/search', json={
        'username': 'alice',
        'investigation_id': investigation_id,
        'timeout': 5,
        'top_sites': 50,
        'report_format': 'pdf',
    })
    assert search_resp.status_code == 202
    search_id = search_resp.json()['id']

    with Session(engine) as session:
        session.add(main.Result(
            search_id=search_id,
            site_name='example',
            username='alice',
            status='Claimed',
            status_text='Claimed',
            url='https://example.com/alice',
            url_main='https://example.com',
            tags_json='["social"]',
            profile_json='{"name": "Alice"}',
        ))
        session.commit()

    pdf_resp = client.get(f'/api/searches/{search_id}/report?format=pdf')
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers['content-type'].startswith('application/pdf')

    delete_resp = client.delete(f'/api/investigations/{investigation_id}')
    assert delete_resp.status_code == 204


def test_run_maigret_handles_search_failures_without_partial_nameerror(monkeypatch):
    class DummySettings:
        def load(self):
            return None

    class DummyDatabase:
        def load_from_path(self, _path):
            return self

        def ranked_sites_dict(self, **kwargs):
            return {'example': object()}

    def fake_search(*args, **kwargs):
        raise RuntimeError('search exploded')

    with Session(engine) as session:
        investigation = main.Investigation(title='Regression case', primary_username='alice')
        session.add(investigation)
        session.commit()
        session.refresh(investigation)
        search = Search(investigation_id=investigation.id, username='alice', options_json='{}')
        session.add(search)
        session.commit()
        session.refresh(search)
        search_id = search.id

    monkeypatch.setattr(main, 'Settings', DummySettings)
    monkeypatch.setattr(main, 'MaigretDatabase', DummyDatabase)
    monkeypatch.setattr(main, 'build_cloudflare_bypass_config', lambda _settings: {})
    monkeypatch.setattr(main.maigret, 'search', fake_search)

    main.run_maigret(search_id, 'alice', {
        'all_sites': False,
        'top_sites': 1,
        'timeout': 5,
        'extract': False,
        'recursive': False,
        'check_domains': False,
        'tags': [],
        'excluded_tags': [],
        'site_list': [],
        'keywords': [],
    })

    with Session(engine) as session:
        updated = session.get(Search, search_id)
        assert updated is not None
        assert updated.status == 'failed'
        assert 'search exploded' in updated.error_message


def test_startup_cleanup_removes_demo_alice_records():
    with Session(engine) as session:
        investigation = main.Investigation(title='Alice demo', primary_username='alice')
        session.add(investigation)
        session.commit()
        session.refresh(investigation)
        session.add(Search(investigation_id=investigation.id, username='alice', options_json='{}'))
        session.commit()

    main.cleanup_demo_records()

    with Session(engine) as session:
        assert session.exec(select(main.Investigation).where(main.Investigation.primary_username == 'alice')).all() == []
        assert session.exec(select(Search).where(Search.username == 'alice')).all() == []


def test_terminal_endpoint_runs_maigret_help_command(client):
    response = client.post('/api/terminal/execute', json={'command': 'python -m maigret --help'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['exit_code'] == 0
    assert 'usage:' in payload['output'].lower()
