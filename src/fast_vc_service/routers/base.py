from fastapi import APIRouter, Response
from loguru import logger
from typing import Dict

from fast_vc_service import __version__ as service_version
from fast_vc_service import __build_date__ as build_date

base_router = APIRouter(tags=["System"])

@base_router.get("/health", summary="Health check endpoint")
async def health_check() -> Dict[str, str]:
    """Check if the service is up and running"""
    resp = {"status": "healthy"}
    logger.info(f"OUT | {resp}")
    return resp

@base_router.get("/version", summary="Get service version")
async def get_version() -> Dict[str, str]:
    """Return the current version of the application"""
    resp = {
        "version": service_version,
        "build_date": build_date
    }
    logger.info(f"OUT | {resp}")
    return resp

