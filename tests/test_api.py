from fastapi.testclient import TestClient

from app.main import app


class FakeRepository:
    def __init__(self) -> None:
        self.closed = False

    def ping(self) -> bool:
        return True

    def stats(self):
        from datetime import UTC, datetime
        from app.models.schemas import StatsResponse

        return StatsResponse(
            conversations=1,
            messages=2,
            entities=3,
            traces=1,
            pending_duplicates=0,
            checked_at=datetime.now(tz=UTC),
        )


class FakeService:
    def __init__(self) -> None:
        self.repository = FakeRepository()


def test_health_endpoint_uses_repository_ping() -> None:
    client = TestClient(app)
    original = app.dependency_overrides.copy()
    from app.routes.api import get_memory_service

    app.dependency_overrides[get_memory_service] = FakeService
    try:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        app.dependency_overrides = original


def test_stats_endpoint_returns_payload() -> None:
    client = TestClient(app)
    original = app.dependency_overrides.copy()
    from app.routes.api import get_memory_service

    app.dependency_overrides[get_memory_service] = FakeService
    try:
        response = client.get("/api/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["entities"] == 3
        assert body["pending_duplicates"] == 0
    finally:
        app.dependency_overrides = original