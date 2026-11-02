from fastapi import FastAPI, Query

from app.errors import AppError, ErrorCode, register_error_handlers


def build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/app-error")
    async def app_error():
        raise AppError(ErrorCode.LIBRARY_PRIVATE, "라이브러리가 비공개입니다.", 403)

    @app.get("/validate")
    async def validate(count: int = Query()):
        return {"count": count}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    return app


async def request(path: str):
    import httpx

    transport = httpx.ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.get(path)


async def test_app_error_uses_common_format():
    res = await request("/app-error")
    assert res.status_code == 403
    assert res.json() == {"error": {"code": "LIBRARY_PRIVATE", "message": "라이브러리가 비공개입니다."}}


async def test_validation_error_maps_to_invalid_input():
    res = await request("/validate?count=abc")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_INPUT"
    assert "count" in res.json()["error"]["message"]


async def test_unknown_route_maps_to_not_found():
    res = await request("/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


async def test_unexpected_error_hides_internal_message():
    res = await request("/boom")
    assert res.status_code == 500
    body = res.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in res.text
