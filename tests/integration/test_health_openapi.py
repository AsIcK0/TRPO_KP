REQUIRED = {
    ("post", "/api/v1/auth/login"), ("get", "/api/v1/auth/me"),
    ("post", "/api/v1/users"), ("get", "/api/v1/users"), ("get", "/api/v1/users/{user_id}"),
    ("patch", "/api/v1/users/{user_id}"), ("post", "/api/v1/users/{user_id}/deactivate"),
    ("get", "/api/v1/departments"), ("post", "/api/v1/departments"), ("patch", "/api/v1/departments/{item_id}"),
    ("get", "/api/v1/positions"), ("post", "/api/v1/positions"), ("patch", "/api/v1/positions/{item_id}"),
    ("get", "/api/v1/document-types"), ("post", "/api/v1/document-types"),
    ("patch", "/api/v1/document-types/{item_id}"),
    ("post", "/api/v1/correspondents"), ("get", "/api/v1/correspondents"),
    ("get", "/api/v1/correspondents/{correspondent_id}"), ("patch", "/api/v1/correspondents/{correspondent_id}"),
    ("post", "/api/v1/incoming"), ("get", "/api/v1/incoming"), ("get", "/api/v1/incoming/{document_id}"),
    ("get", "/api/v1/incoming/by-registration-number/{registration_number}"),
    ("patch", "/api/v1/incoming/{document_id}"), ("delete", "/api/v1/incoming/{document_id}"),
    ("post", "/api/v1/incoming/{document_id}/resolutions"), ("get", "/api/v1/incoming/{document_id}/resolutions"),
    ("patch", "/api/v1/resolutions/{resolution_id}"),
    ("post", "/api/v1/incoming/{document_id}/files"), ("get", "/api/v1/files/{attachment_id}/download"),
    ("get", "/api/v1/incoming/{document_id}/history"), ("post", "/api/v1/incoming/{document_id}/status"),
    ("post", "/api/v1/reports/generate"), ("get", "/api/v1/exports/registration-log"), ("get", "/api/v1/health"),
}


async def test_health_checks_database_and_storage(ctx):
    for url in ("/health", "/api/v1/health"):
        response = await ctx.client.get(url)
        assert response.status_code == 200, response.text
        assert response.json() == {"status": "ok", "database": "ok", "storage": "ok"}


async def test_swagger_and_all_required_endpoints_are_published(ctx):
    assert (await ctx.client.get("/docs")).status_code == 200
    schema = (await ctx.client.get("/openapi.json")).json()
    published = {(method, path) for path, ops in schema["paths"].items() for method in ops}
    assert REQUIRED - published == set()
    assert "password_hash" not in str(schema["components"]["schemas"])
