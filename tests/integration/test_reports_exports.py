import csv
import io
from datetime import timedelta

import pytest

from tests.integration.conftest import assert_error


async def _prepare(ctx):
    done = await ctx.register(summary="Письмо о согласовании проекта")
    await ctx.to_review(done["id"])
    await ctx.resolve(done["id"], "executor1")
    assert (await ctx.execute(done["id"], "executor1")).status_code == 200
    pending = await ctx.register(summary="Запрос; с «кавычками» и \"двойными\"",
                                 correspondent_id=ctx.correspondents[1])
    return done, pending


async def test_csv_registration_log_with_cyrillic(ctx):
    done, pending = await _prepare(ctx)
    response = await ctx.client.get("/api/v1/exports/registration-log", headers=ctx.h("clerk"))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    raw = response.content
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM для Excel

    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
    assert rows[0][0] == "Регистрационный номер" and "Корреспондент" in rows[0]
    by_number = {r[0]: r for r in rows[1:]}
    assert set(by_number) == {done["registration_number"], pending["registration_number"]}
    assert by_number[done["registration_number"]][rows[0].index("Статус")] == "исполнен"
    assert by_number[done["registration_number"]][rows[0].index("Исполнители")] == "Сидорова Мария Игоревна"
    assert by_number[pending["registration_number"]][rows[0].index("Корреспондент")] == "АО «Прогресс-Инжиниринг»"
    assert by_number[pending["registration_number"]][rows[0].index("Краткое содержание")] == pending["summary"]


async def test_csv_filters_and_rbac(ctx):
    done, _ = await _prepare(ctx)
    response = await ctx.client.get("/api/v1/exports/registration-log", params={"status": "исполнен"},
                                    headers=ctx.h("clerk"))
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert [r[0] for r in rows[1:]] == [done["registration_number"]]
    future = await ctx.client.get("/api/v1/exports/registration-log", headers=ctx.h("clerk"),
                                  params={"date_from": (ctx.today + timedelta(days=1)).isoformat()})
    assert len(future.content.decode("utf-8-sig").splitlines()) == 1  # только заголовок
    for login in ("manager", "executor1", "admin"):
        assert_error(await ctx.client.get("/api/v1/exports/registration-log", headers=ctx.h(login)), 403)


@pytest.mark.parametrize("report_type", ["documents", "executors", "deadlines"])
async def test_pdf_reports_are_generated(ctx, report_type):
    await _prepare(ctx)
    payload = {"report_type": report_type, "period_from": (ctx.today - timedelta(days=30)).isoformat(),
               "period_to": ctx.today.isoformat()}
    for login in ("clerk", "manager"):
        response = await ctx.client.post("/api/v1/reports/generate", json=payload, headers=ctx.h(login))
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF") and len(response.content) > 2000
        assert f"report-{report_type}" in response.headers["content-disposition"]


async def test_pdf_report_with_filters_and_validation(ctx):
    await _prepare(ctx)
    payload = {"report_type": "documents", "period_from": ctx.today.isoformat(), "period_to": ctx.today.isoformat(),
               "correspondent_id": str(ctx.correspondents[1]), "status": "зарегистрирован",
               "document_type_id": str(ctx.doc_types[0])}
    assert (await ctx.client.post("/api/v1/reports/generate", json=payload, headers=ctx.h("clerk"))).status_code == 200
    bad = payload | {"period_from": (ctx.today + timedelta(days=1)).isoformat()}
    assert_error(await ctx.client.post("/api/v1/reports/generate", json=bad, headers=ctx.h("clerk")), 422)
    assert_error(await ctx.client.post("/api/v1/reports/generate", json={"report_type": "documents"},
                                       headers=ctx.h("clerk")), 422)  # период обязателен
    for login in ("executor1", "admin"):
        assert_error(await ctx.client.post("/api/v1/reports/generate", json=payload, headers=ctx.h(login)), 403)
