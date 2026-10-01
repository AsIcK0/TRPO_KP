"""Веб-интерфейс раздается тем же FastAPI (/ui), корень перенаправляет на него."""

import httpx

from app.main import app


async def test_ui_is_served_and_root_redirects():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        root = await client.get("/")
        assert root.status_code in (302, 307) and root.headers["location"] == "/ui/"

        page = await client.get("/ui/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert "/ui/app.js" in page.text and "/ui/styles.css" in page.text

        for asset, mime in (("app.js", "javascript"), ("api.js", "javascript"), ("styles.css", "text/css")):
            response = await client.get(f"/ui/{asset}")
            assert response.status_code == 200, asset
            assert mime in response.headers["content-type"], (asset, response.headers["content-type"])

        # Swagger остается на месте
        assert (await client.get("/docs")).status_code == 200
