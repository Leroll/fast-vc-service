from fastapi import APIRouter, Response
from loguru import logger
from typing import Dict

base_router = APIRouter(tags=["System"])

VERSION = "0.1.0"  # You can update this or load from a config file

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
        "version": VERSION,
    }
    logger.info(f"OUT | {resp}")
    return resp

