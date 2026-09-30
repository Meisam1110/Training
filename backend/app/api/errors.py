"""Error envelope: {"error": {"code", "message"(fa), "fields"}}.

Codes from the contract: validation | forbidden | not_found | conflict | upstream.
Additions (see docs/CONTRACT_REQUESTS.md): unauthorized (401), rate_limited (429).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("tms.error")

STATUS = {"validation": 422, "forbidden": 403, "not_found": 404, "conflict": 409, "upstream": 502,
          "unauthorized": 401, "rate_limited": 429}


PYDANTIC_FA = {
    "missing": "الزامی است", "string_too_short": "خیلی کوتاه است", "string_too_long": "خیلی بلند است", "too_short": "تعداد آیتم‌ها کم است",
    "too_long": "تعداد آیتم‌ها زیاد است", "greater_than_equal": "کمتر از حد مجاز است", "greater_than": "کمتر از حد مجاز است",
    "less_than_equal": "بیشتر از حد مجاز است", "less_than": "بیشتر از حد مجاز است", "int_parsing": "باید عدد صحیح باشد",
    "int_type": "باید عدد صحیح باشد", "float_parsing": "باید عدد باشد", "bool_parsing": "باید true یا false باشد",
    "literal_error": "مقدار مجاز نیست", "enum": "مقدار مجاز نیست", "extra_forbidden": "فیلد ناشناخته است",
    "string_pattern_mismatch": "قالب مقدار نادرست است", "string_type": "باید متن باشد", "date_parsing": "تاریخ نامعتبر است",
    "date_from_datetime_parsing": "تاریخ نامعتبر است", "date_type": "تاریخ نامعتبر است", "datetime_parsing": "تاریخ/زمان نامعتبر است",
    "value_error": "مقدار نامعتبر است", "dict_type": "باید شیء باشد", "list_type": "باید فهرست باشد", "json_invalid": "JSON نامعتبر است",
    "decimal_parsing": "باید عدد باشد", "model_attributes_type": "ساختار نامعتبر است", "missing_argument": "الزامی است",
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, fields: dict[str, Any] | None = None, status: int | None = None,
                 headers: dict[str, str] | None = None):
        self.code, self.message, self.fields = code, message, fields or {}
        self.status = status or STATUS[code]
        self.headers = headers or {}


def validation(message: str = "داده‌های ورودی نامعتبر است", **fields: str) -> ApiError:
    return ApiError("validation", message, fields)


def not_found(what: str = "مورد") -> ApiError:
    return ApiError("not_found", f"{what} یافت نشد")


def forbidden(message: str = "دسترسی مجاز نیست") -> ApiError:
    return ApiError("forbidden", message)


def conflict(message: str) -> ApiError:
    return ApiError("conflict", message)


def upstream(message: str) -> ApiError:
    return ApiError("upstream", message)


def _resp(status: int, code: str, message: str, fields: dict | None = None, headers: dict | None = None):
    return JSONResponse({"error": {"code": code, "message": message, "fields": fields or {}}},
                        status_code=status, headers=headers)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, e: ApiError):
        return _resp(e.status, e.code, e.message, e.fields, e.headers)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, e: RequestValidationError):
        fields: dict[str, str] = {}
        for err in e.errors():
            loc = [str(x) for x in err["loc"] if x not in ("body", "query", "path")]
            fields[".".join(loc) or "_"] = PYDANTIC_FA.get(err.get("type", ""), "مقدار نامعتبر است")
        return _resp(422, "validation", "داده‌های ورودی نامعتبر است", fields)

    @app.exception_handler(OverflowError)
    async def _overflow(_: Request, e: OverflowError):
        return _resp(422, "validation", "مقدار عددی خارج از محدوده است")

    @app.exception_handler(DataError)
    async def _dataerr(request: Request, e: DataError):
        log.warning("data error", extra={"path": request.url.path, "exc_type": type(e.orig).__name__})
        return _resp(422, "validation", "مقدار نامعتبر برای پایگاه داده (طول، کاراکتر یا محدوده)")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        code = {404: "not_found", 405: "validation", 401: "unauthorized", 403: "forbidden"}.get(e.status_code, "validation")
        msg = {404: "یافت نشد", 405: "روش درخواست مجاز نیست"}.get(e.status_code, "درخواست نامعتبر")
        return _resp(e.status_code, code, msg)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, e: Exception):
        # message deliberately generic: exception text can contain row values
        log.error("unhandled", exc_info=(type(e), e, e.__traceback__),
                  extra={"path": request.url.path, "request_id": request.scope.get("state", {}).get("request_id")})
        return _resp(500, "upstream", "خطای داخلی سرور", None)
