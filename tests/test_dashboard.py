import pytest
from fastapi.testclient import TestClient

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
