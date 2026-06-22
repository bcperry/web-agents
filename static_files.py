"""Static frontend mounting for the FastAPI application."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


def mount_static_files(application: FastAPI, *, logger: logging.Logger) -> None:
    """Mount frontend static files if the dist directory exists."""
    if not FRONTEND_DIR.is_dir():
        logger.warning("frontend/dist/ not found — static file serving disabled. Run 'cd frontend && npm run build'")
        return

    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    application.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa_catch_all(full_path: str):
        """Serve index.html for all non-API, non-static routes."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        file_path = FRONTEND_DIR / full_path
        if full_path and file_path.is_file() and FRONTEND_DIR in file_path.resolve().parents:
            return FileResponse(str(file_path))

        index_file = FRONTEND_DIR / "index.html"
        if index_file.is_file():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

        raise HTTPException(status_code=404, detail="Frontend not built. Run: cd frontend && npm run build")