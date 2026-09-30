from tests.integration.conftest import assert_error


async def test_admin_creates_user_without_exposing_password_hash(ctx):
    payload = {"full_name": "Новикова Ольга Петровна", "login": "novikova", "email": "Novikova@Example.org",
               "password": "StrongPass1", "role": "executor", "department_id": str(ctx.department)}
    response = await ctx.client.post("/api/v1/users", json=payload, headers=ctx.h("admin"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "novikova@example.org" and body["is_active"] is True
    assert "password_hash" not in body and "password" not in body

    login = await ctx.client.post("/api/v1/auth/login", json={"login": "novikova", "password": "StrongPass1"})
    assert login.status_code == 200

    assert_error(await ctx.client.post("/api/v1/users", json=payload, headers=ctx.h("admin")), 409,
                 "LOGIN_CONFLICT", "login")
    payload |= {"login": "novikova2"}
    assert_error(await ctx.client.post("/api/v1/users", json=payload, headers=ctx.h("admin")), 409,
                 "EMAIL_CONFLICT", "email")


async def test_user_validation_errors(ctx):
    payload = {"full_name": "Тест", "login": "x y", "email": "not-an-email", "password": "123",
               "role": "superuser", "department_id": str(ctx.department)}
    assert_error(await ctx.client.post("/api/v1/users", json=payload, headers=ctx.h("admin")), 422,
                 "VALIDATION_ERROR")


async def test_non_admin_cannot_manage_users(ctx):
    for login in ("clerk", "manager", "executor1"):
        assert_error(await ctx.client.get("/api/v1/users", headers=ctx.h(login)), 403, "FORBIDDEN")
        response = await ctx.client.post(f"/api/v1/users/{ctx.users['executor2']}/deactivate", headers=ctx.h(login))
        assert_error(response, 403, "FORBIDDEN")


async def test_user_list_filter_update_and_no_physical_delete(ctx):
    response = await ctx.client.get("/api/v1/users", params={"role": "executor", "page_size": 1},
                                    headers=ctx.h("admin"))
    body = response.json()
    assert body["total"] == 2 and len(body["items"]) == 1 and body["pages"] == 2

    upd = await ctx.client.patch(f"/api/v1/users/{ctx.users['executor2']}", headers=ctx.h("admin"),
                                 json={"full_name": "Козлов Дмитрий Андреевич (ред.)"})
    assert upd.status_code == 200 and upd.json()["full_name"].endswith("(ред.)")
    assert (await ctx.client.delete(f"/api/v1/users/{ctx.users['executor2']}",
                                    headers=ctx.h("admin"))).status_code == 405
    self_deactivate = await ctx.client.post(f"/api/v1/users/{ctx.users['admin']}/deactivate",
                                            headers=ctx.h("admin"))
    assert_error(self_deactivate, 409, "CANNOT_DEACTIVATE_SELF")


async def test_dictionaries_admin_only_but_types_readable_by_all(ctx):
    created = await ctx.client.post("/api/v1/departments", json={"name": "Отдел кадров"}, headers=ctx.h("admin"))
    assert created.status_code == 201
    assert_error(await ctx.client.post("/api/v1/departments", json={"name": "Отдел кадров"},
                                       headers=ctx.h("admin")), 409, "NAME_CONFLICT")
    assert (await ctx.client.post("/api/v1/positions", json={"name": "Инспектор"},
                                  headers=ctx.h("admin"))).status_code == 201
    assert_error(await ctx.client.post("/api/v1/document-types", json={"name": "Акт"}, headers=ctx.h("clerk")), 403)

    types = await ctx.client.get("/api/v1/document-types", headers=ctx.h("executor1"))
    assert types.status_code == 200 and len(types.json()) == 3
    assert_error(await ctx.client.get("/api/v1/departments", headers=ctx.h("clerk")), 403)
