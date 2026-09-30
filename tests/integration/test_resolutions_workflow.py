from datetime import timedelta

from tests.integration.conftest import assert_error


async def test_manager_creates_resolution_and_document_goes_to_execution(ctx):
    doc = await ctx.register()
    await ctx.to_review(doc["id"])
    resolution = await ctx.resolve(doc["id"], "executor1")
    assert resolution["author"]["id"] == str(ctx.users["manager"])
    assert resolution["status"] == "на исполнении"

    card = (await ctx.client.get(f"/api/v1/incoming/{doc['id']}", headers=ctx.h("clerk"))).json()
    assert card["status"] == "на исполнении"
    assert [e["full_name"] for e in card["executors"]] == ["Сидорова Мария Игоревна"]
    actions = [h["action"] for h in card["history"]]
    assert actions[-2:] == ["resolution_created", "status_changed"]


async def test_resolution_rules(ctx):
    doc = await ctx.register()
    body = {"text": "Подготовить ответ", "assigned_executor_id": str(ctx.users["executor1"]),
            "deadline": (ctx.today + timedelta(days=3)).isoformat()}
    url = f"/api/v1/incoming/{doc['id']}/resolutions"
    # документ еще не передан на рассмотрение
    assert_error(await ctx.client.post(url, json=body, headers=ctx.h("manager")), 409, "INVALID_DOCUMENT_STATE")
    await ctx.to_review(doc["id"])
    # резолюцию создает только руководитель
    for login in ("clerk", "executor1", "admin"):
        assert_error(await ctx.client.post(url, json=body, headers=ctx.h(login)), 403, "FORBIDDEN")
    # исполнителем может быть только активный пользователь с ролью «исполнитель»
    wrong = body | {"assigned_executor_id": str(ctx.users["clerk"])}
    assert_error(await ctx.client.post(url, json=wrong, headers=ctx.h("manager")), 422, field="assigned_executor_id")
    missing = body | {"assigned_executor_id": "00000000-0000-0000-0000-000000000000"}
    assert_error(await ctx.client.post(url, json=missing, headers=ctx.h("manager")), 422)


async def test_executor_sees_only_own_assignments(ctx):
    mine = await ctx.register(summary="Поручение исполнителю 1")
    foreign = await ctx.register(summary="Поручение исполнителю 2")
    for doc, executor in ((mine, "executor1"), (foreign, "executor2")):
        await ctx.to_review(doc["id"])
        await ctx.resolve(doc["id"], executor)

    listing = await ctx.client.get("/api/v1/incoming", headers=ctx.h("executor1"))
    assert [d["id"] for d in listing.json()["items"]] == [mine["id"]]
    assert (await ctx.client.get(f"/api/v1/incoming/{mine['id']}/resolutions",
                                 headers=ctx.h("executor1"))).status_code == 200
    assert_error(await ctx.client.get(f"/api/v1/incoming/{foreign['id']}", headers=ctx.h("executor1")), 403)
    assert_error(await ctx.client.get(f"/api/v1/incoming/{foreign['id']}/resolutions",
                                      headers=ctx.h("executor1")), 403)
    # поиск и фильтрация исполнителю недоступны по матрице прав
    assert_error(await ctx.client.get("/api/v1/incoming", params={"search": "Поручение"},
                                      headers=ctx.h("executor1")), 403)


async def test_executor_attaches_report_and_marks_execution(ctx):
    doc = await ctx.register()
    await ctx.to_review(doc["id"])
    await ctx.resolve(doc["id"], "executor1")

    upload = await ctx.upload(doc["id"], as_user="executor1", name="Отчет об исполнении.pdf")
    assert upload.status_code == 201, upload.text
    assert upload.json()["attachment_type"] == "execution_report"
    assert_error(await ctx.upload(doc["id"], as_user="executor1", attachment_type="source_scan"), 403)

    assert_error(await ctx.execute(doc["id"], "executor2"), 403)  # чужой документ
    done = await ctx.execute(doc["id"], "executor1")
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "исполнен" and body["resolutions"][0]["status"] == "исполнена"
    assert body["resolutions"][0]["executed_at"]
    assert_error(await ctx.execute(doc["id"], "executor1"), 409)  # повторная отметка
    assert (await ctx.set_status(doc["id"], "снят с контроля")).json()["status"] == "снят с контроля"


async def test_document_executed_only_when_all_executors_done(ctx):
    doc = await ctx.register()
    await ctx.to_review(doc["id"])
    await ctx.resolve(doc["id"], "executor1")
    await ctx.resolve(doc["id"], "executor2")

    first = await ctx.execute(doc["id"], "executor1")
    assert first.status_code == 200 and first.json()["status"] == "на исполнении"
    second = await ctx.execute(doc["id"], "executor2")
    assert second.json()["status"] == "исполнен"
    status_entries = [h for h in second.json()["history"] if h["new_status"] == "исполнен"]
    assert len(status_entries) == 1 and status_entries[0]["user"]["id"] == str(ctx.users["executor2"])


async def test_resolution_editable_until_completion(ctx):
    doc = await ctx.register()
    await ctx.to_review(doc["id"])
    resolution = await ctx.resolve(doc["id"], "executor1")
    url = f"/api/v1/resolutions/{resolution['id']}"

    edited = await ctx.client.patch(url, headers=ctx.h("manager"),
                                    json={"text": "Подготовить ответ до пятницы",
                                          "assigned_executor_id": str(ctx.users["executor2"])})
    assert edited.status_code == 200, edited.text
    assert edited.json()["assigned_executor"]["id"] == str(ctx.users["executor2"])
    assert_error(await ctx.client.patch(url, json={"text": "Попытка"}, headers=ctx.h("clerk")), 403)

    assert (await ctx.execute(doc["id"], "executor2")).status_code == 200
    assert_error(await ctx.client.patch(url, json={"text": "Поздно"}, headers=ctx.h("manager")), 409,
                 "RESOLUTION_LOCKED")


async def test_full_lifecycle_to_archive(ctx):
    archived = await ctx.archived_document()
    statuses = [h["new_status"] for h in archived["history"] if h["new_status"]]
    assert statuses == ["зарегистрирован", "на рассмотрении", "на исполнении", "исполнен", "снят с контроля",
                        "в архиве"]
