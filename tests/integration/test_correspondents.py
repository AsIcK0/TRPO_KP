from tests.integration.conftest import assert_error


async def test_clerk_creates_edits_and_finds_correspondent(ctx):
    payload = {"name": "ООО «Альфа-Логистик»", "inn": "7709000009", "address": "г. Ростов-на-Дону",
               "phone": "+7 863 100-00-09", "email": "Office@Alfa.example", "signer_full_name": "Гусева Л. Р."}
    created = await ctx.client.post("/api/v1/correspondents", json=payload, headers=ctx.h("clerk"))
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["email"] == "office@alfa.example"

    updated = await ctx.client.patch(f"/api/v1/correspondents/{cid}", json={"phone": "+7 863 555-55-55"},
                                     headers=ctx.h("clerk"))
    assert updated.status_code == 200 and updated.json()["phone"] == "+7 863 555-55-55"

    found = await ctx.client.get("/api/v1/correspondents", params={"search": "альфа"}, headers=ctx.h("clerk"))
    assert [c["id"] for c in found.json()["items"]] == [cid]


async def test_correspondent_validation_and_rbac(ctx):
    assert_error(await ctx.client.post("/api/v1/correspondents", json={"name": "ООО «Тест»", "inn": "12AB"},
                                       headers=ctx.h("clerk")), 422, "VALIDATION_ERROR", "inn")
    for login in ("manager", "executor1", "admin"):
        response = await ctx.client.post("/api/v1/correspondents", json={"name": "ООО «Тест»"}, headers=ctx.h(login))
        assert_error(response, 403, "FORBIDDEN")
