from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_db
from app.main import app


class WorkingSession:
    def execute(self, statement: object) -> None:
        pass


class BrokenSession:
    def execute(self, statement: object) -> None:
        raise SQLAlchemyError


def working_db() -> Iterator[WorkingSession]:
    yield WorkingSession()


def broken_db() -> Iterator[BrokenSession]:
    yield BrokenSession()


def test_health_ok() -> None:
    app.dependency_overrides[get_db] = working_db
    client = TestClient(app)
    response = client.get("/api/health")
    app.dependency_overrides.clear()
    assert response.json() == {"status": "ok"}
    assert response.status_code == 200


def test_health_database_down() -> None:
    app.dependency_overrides[get_db] = broken_db
    client = TestClient(app)
    response = client.get("/api/health")
    app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unreachable"}
