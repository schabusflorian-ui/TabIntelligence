"""Tests for OpenAPI metadata and tag descriptions."""


def test_openapi_info(test_client_with_db):
    """OpenAPI spec should include title, version, description, contact, license."""
    response = test_client_with_db.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    assert spec["info"]["title"] == "TabIntelligence"
    assert "version" in spec["info"]
    assert "extraction" in spec["info"]["description"].lower()
    assert spec["info"]["contact"]["name"] == "TabIntelligence"
    assert spec["info"]["license"]["name"] == "Proprietary"


def test_openapi_tags(test_client_with_db):
    """OpenAPI spec should have 8 tags with descriptions."""
    response = test_client_with_db.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    tags = spec.get("tags", [])
    tag_names = {t["name"] for t in tags}

    expected = {
        "entities",
        "jobs",
        "files",
        "taxonomy",
        "analytics",
        "corrections",
        "admin-dlq",
        "health",
    }
    assert expected == tag_names

    # Each tag should have a description
    for tag in tags:
        assert "description" in tag and len(tag["description"]) > 10, (
            f"Tag '{tag['name']}' missing or empty description"
        )
