from tests.integration.conftest import assert_error


async def test_login_success_returns_token_and_role(ctx):
    response = await ctx.client.post("/api/v1/auth/login", json={"login": "clerk", "password": "clerk123"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["role"] == "clerk" and body["user"]["login"] == "clerk"
    assert "password" not in response.text and "password_hash" not in response.text

    me = await ctx.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert "document:register" in me.json()["permissions"]


async def test_wrong_password_and_unknown_login_return_401(ctx):
    for payload in ({"login": "clerk", "password": "wrong-pass"}, {"login": "nobody", "password": "clerk123"}):
        response = await ctx.client.post("/api/v1/auth/login", json=payload)
        assert_error(response, 401, "INVALID_CREDENTIALS")


async def test_deactivated_user_cannot_login_nor_use_old_token(ctx):
    old_headers = ctx.h("executor2")
    response = await ctx.client.post(f"/api/v1/users/{ctx.users['executor2']}/deactivate", headers=ctx.h("admin"))
    assert response.status_code == 200 and response.json()["is_active"] is False

    login = await ctx.client.post("/api/v1/auth/login", json={"login": "executor2", "password": "executor123"})
    assert_error(login, 403, "USER_INACTIVE")
    assert_error(await ctx.client.get("/api/v1/auth/me", headers=old_headers), 403, "USER_INACTIVE")


async def test_role_is_always_loaded_from_db(ctx):
    headers = ctx.h("executor1")  # токен выпущен, пока пользователь был исполнителем
    response = await ctx.client.patch(f"/api/v1/users/{ctx.users['executor1']}", json={"role": "clerk"},
                                      headers=ctx.h("admin"))
    assert response.status_code == 200
    me = await ctx.client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["role"] == "clerk"
    # новые права действуют сразу: бывший исполнитель теперь может выгрузить журнал
    assert (await ctx.client.get("/api/v1/exports/registration-log", headers=headers)).status_code == 200


async def test_missing_or_invalid_token_returns_401(ctx):
    assert_error(await ctx.client.get("/api/v1/incoming"), 401, "UNAUTHORIZED")
    bad = await ctx.client.get("/api/v1/incoming", headers={"Authorization": "Bearer not-a-token"})
    assert_error(bad, 401, "INVALID_TOKEN")
