"""Tests for entity CRUD endpoints (GET/POST/PATCH/DELETE /api/v1/entities)."""
import pytest
from uuid import uuid4


class TestEntityList:
    """Test GET /api/v1/entities."""

    def test_list_entities_empty(self, test_client_with_db):
        response = test_client_with_db.get("/api/v1/entities/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["entities"] == []

    def test_list_entities_with_data(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            crud.create_entity(session, name="Acme Corp", industry="Technology")
            crud.create_entity(session, name="Beta Inc", industry="Finance")
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/entities/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    def test_list_entities_pagination(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            for i in range(5):
                crud.create_entity(session, name=f"Entity {i}")
        finally:
            session.close()

        response = test_client_with_db.get("/api/v1/entities/?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2


class TestEntityCreate:
    """Test POST /api/v1/entities."""

    def test_create_entity(self, test_client_with_db):
        response = test_client_with_db.post(
            "/api/v1/entities/",
            json={"name": "Acme Corp", "industry": "Technology"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Acme Corp"
        assert data["industry"] == "Technology"
        assert "id" in data

    def test_create_entity_name_only(self, test_client_with_db):
        response = test_client_with_db.post(
            "/api/v1/entities/",
            json={"name": "Simple Entity"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Simple Entity"
        assert data["industry"] is None

    def test_create_entity_missing_name(self, test_client_with_db):
        response = test_client_with_db.post("/api/v1/entities/", json={})
        assert response.status_code == 422  # Validation error


class TestEntityGet:
    """Test GET /api/v1/entities/{entity_id}."""

    def test_get_entity(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Test Corp", industry="Finance")
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.get(f"/api/v1/entities/{entity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Corp"
        assert data["industry"] == "Finance"
        assert data["patterns_count"] == 0
        assert data["files_count"] == 0

    def test_get_entity_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        response = test_client_with_db.get(f"/api/v1/entities/{fake_id}")
        assert response.status_code == 404

    def test_get_entity_invalid_id(self, test_client_with_db):
        response = test_client_with_db.get("/api/v1/entities/not-a-uuid")
        assert response.status_code == 400


class TestEntityUpdate:
    """Test PATCH /api/v1/entities/{entity_id}."""

    def test_update_entity_name(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Old Name")
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.patch(
            f"/api/v1/entities/{entity_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_update_entity_industry(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Corp", industry="Tech")
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.patch(
            f"/api/v1/entities/{entity_id}",
            json={"industry": "Finance"},
        )
        assert response.status_code == 200
        assert response.json()["industry"] == "Finance"

    def test_update_entity_no_fields(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Corp")
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.patch(
            f"/api/v1/entities/{entity_id}",
            json={},
        )
        assert response.status_code == 400

    def test_update_entity_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        response = test_client_with_db.patch(
            f"/api/v1/entities/{fake_id}",
            json={"name": "X"},
        )
        assert response.status_code == 404


class TestEntityDelete:
    """Test DELETE /api/v1/entities/{entity_id}."""

    def test_delete_entity(self, test_client_with_db, test_db):
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="To Delete")
            entity_id = str(entity.id)
        finally:
            session.close()

        response = test_client_with_db.delete(f"/api/v1/entities/{entity_id}")
        assert response.status_code == 204

        # Verify it's gone
        response2 = test_client_with_db.get(f"/api/v1/entities/{entity_id}")
        assert response2.status_code == 404

    def test_delete_entity_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        response = test_client_with_db.delete(f"/api/v1/entities/{fake_id}")
        assert response.status_code == 404

    def test_delete_entity_invalid_id(self, test_client_with_db):
        response = test_client_with_db.delete("/api/v1/entities/not-a-uuid")
        assert response.status_code == 400


class TestEntityAuth:
    """Test entity endpoints require authentication."""

    def test_list_requires_auth(self, unauthenticated_client):
        response = unauthenticated_client.get("/api/v1/entities/")
        assert response.status_code in (401, 403)

    def test_create_requires_auth(self, unauthenticated_client):
        response = unauthenticated_client.post(
            "/api/v1/entities/",
            json={"name": "Test"},
        )
        assert response.status_code in (401, 403)


class TestEntityCRUD:
    """Test entity CRUD functions directly."""

    def test_create_and_get(self, db_session):
        from src.db import crud

        entity = crud.create_entity(db_session, name="Test", industry="Tech")
        assert entity.name == "Test"
        assert entity.industry == "Tech"

        fetched = crud.get_entity(db_session, entity.id)
        assert fetched is not None
        assert fetched.name == "Test"

    def test_list_entities(self, db_session):
        from src.db import crud

        crud.create_entity(db_session, name="A")
        crud.create_entity(db_session, name="B")
        entities = crud.list_entities(db_session)
        assert len(entities) == 2

    def test_update_entity(self, db_session):
        from src.db import crud

        entity = crud.create_entity(db_session, name="Old")
        updated = crud.update_entity(db_session, entity.id, name="New")
        assert updated.name == "New"

    def test_delete_entity(self, db_session):
        from src.db import crud

        entity = crud.create_entity(db_session, name="Delete Me")
        assert crud.delete_entity(db_session, entity.id) is True
        assert crud.get_entity(db_session, entity.id) is None

    def test_delete_nonexistent(self, db_session):
        from src.db import crud
        assert crud.delete_entity(db_session, uuid4()) is False
