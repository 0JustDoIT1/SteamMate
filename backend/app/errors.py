import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    LIBRARY_PRIVATE = "LIBRARY_PRIVATE"
    WISHLIST_PRIVATE = "WISHLIST_PRIVATE"
    STEAM_RATE_LIMITED = "STEAM_RATE_LIMITED"
    STEAM_UNAVAILABLE = "STEAM_UNAVAILABLE"
    STEAM_TIMEOUT = "STEAM_TIMEOUT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_NOT_READY = "DATA_NOT_READY"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTH_FAILED = "AUTH_FAILED"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(code: ErrorCode, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.status_code)


async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in exc.errors())
    return error_response(ErrorCode.INVALID_INPUT, f"잘못된 입력: {fields}", 422)


async def _handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return error_response(ErrorCode.NOT_FOUND, "요청한 경로를 찾을 수 없습니다.", 404)
    code = ErrorCode.INVALID_INPUT if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR
    return error_response(code, str(exc.detail), exc.status_code)


async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    # 내부 예외 메시지는 응답에 노출하지 않는다.
    logger.exception("unhandled error: %s", type(exc).__name__)
    return error_response(ErrorCode.INTERNAL_ERROR, "서버 내부 오류가 발생했습니다.", 500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected)
