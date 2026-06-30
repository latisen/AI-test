from __future__ import annotations

import traceback

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings

app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
	return JSONResponse(
		status_code=500,
		content={
			"detail": f"Unhandled server error: {exc}",
			"traceback": traceback.format_exc(limit=4),
		},
	)


app.include_router(router)
