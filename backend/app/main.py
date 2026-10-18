"""FastAPI composition: security middleware, readiness, and focused route groups."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .api import accounts, cases, demo, documents, evidence, exports
from .api.accounts import attempts as attempts
from .config import settings
from .db import engine


@asynccontextmanager
async def lifespan(app):
    settings().storage_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="DocVerify", version="2.0.0", lifespan=lifespan)
log = logging.getLogger(__name__)


@app.exception_handler(SQLAlchemyError)
async def database_failure(request, error):
    log.error("database_request_failed error_type=%s", type(error).__name__)
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable; please retry shortly"}
    )


@app.middleware("http")
async def browser_security(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin.rstrip("/") != settings().app_origin.rstrip("/")
    ):
        return Response("Origin is not allowed", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/api/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT revision FROM documents LIMIT 1"))
        return {"status": "ok", "database": "ready"}
    except Exception:
        raise HTTPException(503, "Database unavailable or migrations not applied")


for route_group in (accounts, cases, documents, evidence, exports, demo):
    app.include_router(route_group.router)
