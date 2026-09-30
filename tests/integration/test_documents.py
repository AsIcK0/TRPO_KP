import asyncio
import re
from datetime import timedelta

from tests.integration.conftest import assert_error


async def test_register_document_assigns_number_date_and_history(ctx):
    doc = await ctx.register()
    assert re.fullmatch(rf"ВХ-{ctx.today.year}-\d{{6}}", doc["registration_number"])
    assert doc["registration_number"].endswith("000001")
    assert doc["registration_date"] == ctx.today.isoformat()
    assert doc["status"] == "зарегистрирован"
    assert doc["history"][0]["action"] == "document_registered"
    assert doc["history"][0]["new_status"] == "зарегистрирован"
    assert doc["history"][0]["user"]["id"] == str(ctx.users["clerk"])

    second = await ctx.register()
    assert second["registration_number"].endswith("000002")


async def test_parallel_registration_produces_unique_numbers(ctx):
    docs = await asyncio.gather(*(ctx.register(summary=f"Параллельная регистрация №{i}") for i in range(12)))
    numbers = [d["registration_number"] for d in docs]
    assert len(set(numbers)) == 12
    assert sorted(int(n[-6:]) for n in numbers) == list(range(1, 13))  # без пропусков и коллизий


async def test_deadline_before_registration_is_rejected(ctx):
    payload = {"received_date": ctx.today.isoformat(), "correspondent_id": str(ctx.correspondents[0]),
               "summary": "Проверка сроков", "document_type_id": str(ctx.doc_types[0]), "page_count": 1,
               "execution_deadline": (ctx.today - timedelta(days=1)).isoformat()}
    response = await ctx.client.post("/api/v1/incoming", json=payload, headers=ctx.h("clerk"))
    assert_error(response, 422, "VALIDATION_ERROR", "execution_deadline")


async def test_registration_integrity_checks(ctx):
    base = {"received_date": ctx.today.isoformat(), "correspondent_id": str(ctx.correspondents[0]),
            "summary": "Проверка целостности", "document_type_id": str(ctx.doc_types[0]), "page_count": 2,
            "execution_deadline": (ctx.today + timedelta(days=5)).isoformat()}
    cases = [
        ({"page_count": 0}, "page_count"),
        ({"correspondent_id": "00000000-0000-0000-0000-000000000000"}, "correspondent_id"),
        ({"document_type_id": "00000000-0000-0000-0000-000000000000"}, "document_type_id"),
        ({"document_type_id": str(ctx.inactive_type)}, "document_type_id"),
        ({"received_date": (ctx.today + timedelta(days=1)).isoformat()}, "received_date"),
    ]
    for override, field in cases:
        response = await ctx.client.post("/api/v1/incoming", json=base | override, headers=ctx.h("clerk"))
        assert_error(response, 422, "VALIDATION_ERROR", field)


async def test_only_clerk_registers_and_edits(ctx):
    doc = await ctx.register()
    for login in ("manager", "executor1", "admin"):
        response = await ctx.client.patch(f"/api/v1/incoming/{doc['id']}", json={"page_count": 5},
                                          headers=ctx.h(login))
        assert_error(response, 403, "FORBIDDEN")
    edited = await ctx.client.patch(f"/api/v1/incoming/{doc['id']}", json={"page_count": 5, "summary": "Уточнено"},
                                    headers=ctx.h("clerk"))
    assert edited.status_code == 200
    body = edited.json()
    assert body["page_count"] == 5
    change = next(h for h in body["history"] if h["action"] == "document_updated")
    assert change["metadata"]["changes"]["page_count"] == {"old": 3, "new": 5}


async def test_status_change_is_written_to_history(ctx):
    doc = await ctx.register()
    response = await ctx.set_status(doc["id"], "на рассмотрении", comment="Передано руководителю")
    assert response.status_code == 200 and response.json()["status"] == "на рассмотрении"

    history = (await ctx.client.get(f"/api/v1/incoming/{doc['id']}/history", headers=ctx.h("clerk"))).json()
    entry = history[-1]
    assert (entry["action"], entry["old_status"], entry["new_status"]) == (
        "status_changed", "зарегистрирован", "на рассмотрении")
    assert entry["comment"] == "Передано руководителю"
    assert entry["user"]["id"] == str(ctx.users["clerk"]) and entry["created_at"]


async def test_invalid_transition_returns_409_and_role_check_returns_403(ctx):
    doc = await ctx.register()
    assert_error(await ctx.set_status(doc["id"], "исполнен"), 409, "INVALID_STATUS_TRANSITION", "status")
    assert_error(await ctx.set_status(doc["id"], "в архиве"), 409, "INVALID_STATUS_TRANSITION")
    assert_error(await ctx.set_status(doc["id"], "на рассмотрении", as_user="manager"), 403, "FORBIDDEN")
    assert_error(await ctx.set_status(doc["id"], "на рассмотрении", as_user="admin"), 403, "FORBIDDEN")
    history = (await ctx.client.get(f"/api/v1/incoming/{doc['id']}/history", headers=ctx.h("clerk"))).json()
    assert len(history) == 1  # отклоненные попытки не пишутся в историю как смена статуса


async def test_history_is_read_only(ctx):
    doc = await ctx.register()
    url = f"/api/v1/incoming/{doc['id']}/history"
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert (await ctx.client.request(method, url, headers=ctx.h("admin"))).status_code == 405


async def test_archived_document_cannot_be_edited(ctx):
    doc = await ctx.archived_document()
    assert doc["status"] == "в архиве" and doc["archived_at"]
    response = await ctx.client.patch(f"/api/v1/incoming/{doc['id']}", json={"summary": "Попытка изменить"},
                                      headers=ctx.h("clerk"))
    assert_error(response, 409, "DOCUMENT_ARCHIVED")
    assert_error(await ctx.upload(doc["id"], as_user="clerk"), 409, "DOCUMENT_ARCHIVED")


async def test_admin_annuls_document_back_to_registered(ctx):
    doc = await ctx.archived_document()
    response = await ctx.set_status(doc["id"], "зарегистрирован", as_user="admin", comment="Ошибочная регистрация")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "зарегистрирован" and body["archived_at"] is None
    assert body["history"][-1]["action"] == "document_annulled"
    assert_error(await ctx.set_status(doc["id"], "зарегистрирован", as_user="admin"), 409)  # уже зарегистрирован


async def test_only_admin_can_delete_document(ctx):
    doc = await ctx.register()
    upload = await ctx.upload(doc["id"], as_user="clerk")
    assert upload.status_code == 201
    for login in ("clerk", "manager", "executor1"):
        assert_error(await ctx.client.delete(f"/api/v1/incoming/{doc['id']}", headers=ctx.h(login)), 403)

    assert (await ctx.client.delete(f"/api/v1/incoming/{doc['id']}", headers=ctx.h("admin"))).status_code == 204
    assert_error(await ctx.client.get(f"/api/v1/incoming/{doc['id']}", headers=ctx.h("clerk")), 404, "NOT_FOUND")
    assert_error(await ctx.client.get(f"/api/v1/files/{upload.json()['id']}/download", headers=ctx.h("clerk")), 404)


async def test_admin_views_but_cannot_search(ctx):
    doc = await ctx.register()
    assert (await ctx.client.get(f"/api/v1/incoming/{doc['id']}", headers=ctx.h("admin"))).status_code == 200
    assert (await ctx.client.get("/api/v1/incoming", headers=ctx.h("admin"))).json()["total"] == 1
    assert_error(await ctx.client.get("/api/v1/incoming", params={"status": "зарегистрирован"},
                                      headers=ctx.h("admin")), 403, "FORBIDDEN")
