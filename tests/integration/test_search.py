from datetime import timedelta

from tests.integration.conftest import assert_error


async def _search(ctx, login="clerk", **params):
    response = await ctx.client.get("/api/v1/incoming", params=params, headers=ctx.h(login))
    assert response.status_code == 200, response.text
    return response.json()


async def _dataset(ctx):
    a = await ctx.register(summary="Претензия по качеству поставленного оборудования",
                           correspondent_id=ctx.correspondents[0], document_type_id=ctx.doc_types[1])
    b = await ctx.register(summary="Запрос сведений о договоре", correspondent_id=ctx.correspondents[1])
    c = await ctx.register(summary="Уведомление о проверке", correspondent_id=ctx.correspondents[1])
    await ctx.to_review(b["id"])
    await ctx.resolve(b["id"], "executor2")
    # документ «a» зарегистрирован 20 дней назад
    await ctx.sql("UPDATE incoming_documents SET received_date = :d, registration_date = :d WHERE id = :id",
                  d=ctx.today - timedelta(days=20), id=a["id"])
    return a, b, c


async def test_search_by_registration_number(ctx):
    a, b, _ = await _dataset(ctx)
    found = await _search(ctx, registration_number=b["registration_number"][-6:])
    assert [d["id"] for d in found["items"]] == [b["id"]]

    exact = await ctx.client.get(f"/api/v1/incoming/by-registration-number/{a['registration_number']}",
                                 headers=ctx.h("manager"))
    assert exact.status_code == 200 and exact.json()["id"] == a["id"]
    missing = await ctx.client.get("/api/v1/incoming/by-registration-number/ВХ-1999-000001", headers=ctx.h("clerk"))
    assert_error(missing, 404, "NOT_FOUND")


async def test_search_by_correspondent_status_type_and_executor(ctx):
    a, b, c = await _dataset(ctx)
    by_corr = await _search(ctx, correspondent_id=str(ctx.correspondents[1]))
    assert {d["id"] for d in by_corr["items"]} == {b["id"], c["id"]}
    by_status = await _search(ctx, login="manager", status="на исполнении")
    assert [d["id"] for d in by_status["items"]] == [b["id"]]
    by_type = await _search(ctx, document_type_id=str(ctx.doc_types[1]))
    assert [d["id"] for d in by_type["items"]] == [a["id"]]
    by_executor = await _search(ctx, executor_id=str(ctx.users["executor2"]))
    assert [d["id"] for d in by_executor["items"]] == [b["id"]]
    assert by_executor["items"][0]["executors"][0]["full_name"] == "Козлов Дмитрий Андреевич"


async def test_filter_by_dates(ctx):
    a, b, c = await _dataset(ctx)
    old = await _search(ctx, date_to=(ctx.today - timedelta(days=10)).isoformat())
    assert [d["id"] for d in old["items"]] == [a["id"]]
    recent = await _search(ctx, date_from=ctx.today.isoformat(), date_to=ctx.today.isoformat())
    assert {d["id"] for d in recent["items"]} == {b["id"], c["id"]}
    bad = await ctx.client.get("/api/v1/incoming", headers=ctx.h("clerk"),
                               params={"date_from": ctx.today.isoformat(),
                                       "date_to": (ctx.today - timedelta(days=1)).isoformat()})
    assert_error(bad, 422, "VALIDATION_ERROR")


async def test_keyword_search_is_case_insensitive_and_covers_correspondent(ctx):
    a, b, c = await _dataset(ctx)
    assert [d["id"] for d in (await _search(ctx, search="ПРЕТЕНЗИЯ"))["items"]] == [a["id"]]
    by_name = await _search(ctx, search="прогресс")
    assert {d["id"] for d in by_name["items"]} == {b["id"], c["id"]}
    assert (await _search(ctx, search="100%_"))["total"] == 0  # спецсимволы LIKE экранируются


async def test_pagination_and_sorting(ctx):
    await _dataset(ctx)
    page1 = await _search(ctx, page=1, page_size=2, sort="registration_number")
    page2 = await _search(ctx, page=2, page_size=2, sort="registration_number")
    assert (page1["total"], page1["pages"], len(page1["items"]), len(page2["items"])) == (3, 2, 2, 1)
    numbers = [d["registration_number"] for d in page1["items"] + page2["items"]]
    assert numbers == sorted(numbers)
    desc = await _search(ctx, sort="-registration_number")
    assert [d["registration_number"] for d in desc["items"]] == sorted(numbers, reverse=True)
    assert_error(await ctx.client.get("/api/v1/incoming", params={"sort": "password_hash"},
                                      headers=ctx.h("clerk")), 422)


async def test_deadline_control_overdue_and_warning(ctx):
    overdue = await ctx.register(summary="Просроченный документ")
    warning = await ctx.register(summary="Срок близок", execution_deadline=ctx.today + timedelta(days=2))
    normal = await ctx.register(summary="Срок далеко", execution_deadline=ctx.today + timedelta(days=30))
    await ctx.sql("UPDATE incoming_documents SET received_date = :r, registration_date = :r, "
                  "execution_deadline = :d WHERE id = :id",
                  r=ctx.today - timedelta(days=15), d=ctx.today - timedelta(days=2), id=overdue["id"])

    card = (await ctx.client.get(f"/api/v1/incoming/{overdue['id']}", headers=ctx.h("clerk"))).json()
    assert (card["deadline_state"], card["is_overdue"], card["days_left"]) == ("overdue", True, -2)
    assert [d["id"] for d in (await _search(ctx, deadline_state="overdue"))["items"]] == [overdue["id"]]
    assert [d["id"] for d in (await _search(ctx, deadline_state="warning"))["items"]] == [warning["id"]]
    listing = {d["id"]: d["deadline_state"] for d in (await _search(ctx))["items"]}
    assert listing[normal["id"]] == "ok"
