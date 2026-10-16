import pytest


@pytest.fixture
def request_input():
    from lab.api import example_request

    request = example_request("work_cycle")
    request["variants"] = request["variants"][:1]  # S-LAB-08, staffed_36.
    return request


@pytest.fixture
def clock():
    class Clock:
        value = 1000.0

        def __call__(self):
            return self.value

        def advance(self, seconds):
            self.value += seconds

    return Clock()


@pytest.fixture
def service(tmp_path):
    from fastapi.testclient import TestClient
    from lab_server.app import create_app

    db, store = tmp_path / "jobs.sqlite3", tmp_path / "store"
    app = create_app(db, store, {"RATE_BURST": 1000})
    with TestClient(app) as client:
        yield client, app, db, store
