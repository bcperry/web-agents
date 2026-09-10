"""
FastAPI application entry point.

Two-tier architecture: FastAPI backend serving REST API at /api/ and
React SPA static files from frontend/dist/.
"""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_factory import close_azure_credential
from api_routes import autonomous as autonomous_routes
from api_routes import agent_views, profiles, sessions, skills, system, user_data
from app_context import get_skills_dir, session_context
from autonomous import get_autonomous_config, seed_autonomous_directives
from autonomous_scheduler import AutonomousScheduler, scheduler_enabled
from cosmos_memory import close_cosmos, cosmos_config_summary, require_cosmos_configured
import session_data
from skills_manager import seed_skills
from static_files import mount_static_files

load_dotenv()

logging.basicConfig(level=logging.INFO)
logging.getLogger("azure.cosmos").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler: startup, scheduler, and cleanup."""
    require_cosmos_configured()
    cfg = cosmos_config_summary()
    logger.info(
        "Cosmos memory enabled — endpoint=%s database=%s messages=%s conversations=%s auth=%s",
        cfg["endpoint"],
        cfg["database"],
        cfg["messages_container"],
        cfg["conversations_container"],
        cfg["auth"],
    )

    try:
        seeded = await seed_autonomous_directives()
        autonomous_config = await get_autonomous_config()
        logger.info(
            "Autonomous mode — enabled=%s directives=%d (seeded %d) system_identity=%s",
            autonomous_config.enabled,
            len(autonomous_config.directives),
            seeded,
            autonomous_config.system_user_id,
        )
    except Exception:
        logger.warning("Failed to load/seed autonomous config at startup", exc_info=True)

    try:
        skills_seeded = await seed_skills(get_skills_dir())
        logger.info("Skills — seeded %d default skill(s) from ./skills into Cosmos", skills_seeded)
    except Exception:
        logger.warning("Failed to seed skills at startup", exc_info=True)

    autonomous_scheduler = None
    if scheduler_enabled():
        try:
            autonomous_scheduler = AutonomousScheduler(session_context, logger=logger)
            await autonomous_scheduler.start()
            logger.info("Autonomous scheduler started (in-process, Cosmos lease)")
        except Exception:
            logger.error("Failed to start autonomous scheduler", exc_info=True)
            autonomous_scheduler = None

    yield

    if autonomous_scheduler is not None:
        try:
            await autonomous_scheduler.stop()
        except Exception:
            logger.debug("Error stopping autonomous scheduler", exc_info=True)
    session_count = len(session_data._sessions)
    for session_id in list(session_data._sessions):
        await session_data.close_session(session_id)
    await close_cosmos()
    await close_azure_credential()
    logger.info("Cleaned up %d sessions on shutdown", session_count)


app = FastAPI(
    title="Agent Framework API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    system.router,
    profiles.router,
    skills.router,
    sessions.router,
    agent_views.router,
    autonomous_routes.router,
    user_data.router,
):
    app.include_router(router)

mount_static_files(app, logger=logger)