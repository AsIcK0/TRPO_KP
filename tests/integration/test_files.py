import uuid
from urllib.parse import unquote

from app.db.session import get_sessionmaker
from app.models.entities import Attachment
from app.storage.s3 import get_storage
from tests.integration.conftest import PDF_BYTES, PNG_BYTES, assert_error


async def test_clerk_uploads_scan_to_s3_and_downloads_it(ctx):
    doc = await ctx.register()
    upload = await ctx.upload(doc["id"], as_user="clerk", name="Скан письма №15.pdf")
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["attachment_type"] == "source_scan" and attachment["size_bytes"] == len(PDF_BYTES)

    card = (await ctx.client.get(f"/api/v1/incoming/{doc['id']}", headers=ctx.h("clerk"))).json()
    assert [a["id"] for a in card["attachments"]] == [attachment["id"]]
    assert card["history"][-1]["action"] == "file_attached"

    download = await ctx.client.get(f"/api/v1/files/{attachment['id']}/download", headers=ctx.h("clerk"))
    assert download.status_code == 200
    assert download.content == PDF_BYTES
    assert download.headers["content-type"] == "application/pdf"
    assert "Скан письма №15.pdf" in unquote(download.headers["content-disposition"])


async def test_storage_key_is_server_generated(ctx):
    doc = await ctx.register()
    upload = await ctx.upload(doc["id"], as_user="clerk", name="../../etc/passwd.png", content=PNG_BYTES,
                              mime="image/png")
    assert upload.status_code == 201, upload.text
    assert upload.json()["original_filename"] == "passwd.png"
    async with get_sessionmaker()() as session:
        stored = await session.get(Attachment, uuid.UUID(upload.json()["id"]))
    assert stored.storage_key.startswith(f"documents/{doc['id']}/") and stored.storage_key.endswith(".png")
    assert "passwd" not in stored.storage_key and ".." not in stored.storage_key
    assert await get_storage().exists(stored.storage_key)


async def test_download_forbidden_without_rights(ctx):
    doc = await ctx.register()
    await ctx.to_review(doc["id"])
    await ctx.resolve(doc["id"], "executor1")
    attachment = (await ctx.upload(doc["id"], as_user="clerk")).json()
    url = f"/api/v1/files/{attachment['id']}/download"

    assert_error(await ctx.client.get(url), 401)
    assert_error(await ctx.client.get(url, headers=ctx.h("executor2")), 403, "FORBIDDEN")
    assert (await ctx.client.get(url, headers=ctx.h("executor1"))).status_code == 200
    assert (await ctx.client.get(url, headers=ctx.h("manager"))).status_code == 200


async def test_invalid_uploads_are_rejected(ctx):
    doc = await ctx.register()
    cases = [
        (dict(name="virus.exe", content=b"MZ\x90\x00", mime="application/octet-stream"), 422,
         "UNSUPPORTED_FILE_TYPE"),
        (dict(name="fake.pdf", content=b"MZ\x90\x00", mime="application/pdf"), 422, "FILE_CONTENT_MISMATCH"),
        (dict(name="scan.pdf", content=PDF_BYTES, mime="image/png"), 422, "UNSUPPORTED_FILE_TYPE"),
        (dict(name="big.pdf", content=b"%PDF" + b"0" * (1024 * 1024 + 10), mime="application/pdf"), 413,
         "FILE_TOO_LARGE"),
    ]
    for kwargs, status, code in cases:
        assert_error(await ctx.upload(doc["id"], as_user="clerk", **kwargs), status, code)
    assert_error(await ctx.upload(doc["id"], as_user="manager"), 403)  # руководитель файлы не прикрепляет
    card = (await ctx.client.get(f"/api/v1/incoming/{doc['id']}", headers=ctx.h("clerk"))).json()
    assert card["attachments"] == []
