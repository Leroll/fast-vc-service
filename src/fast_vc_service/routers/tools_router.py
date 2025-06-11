from fastapi import APIRouter, HTTPException, Query, Path
from loguru import logger
from typing import Optional
from pathlib import Path

from fast_vc_service.tools.session_data_manager import SessionDataManager

tools_router = APIRouter(tags=["Tools"], prefix="/tools")
data_manager = SessionDataManager()

@tools_router.get("/session/{session_id}", summary="Retrieve compressed session data")
async def get_session_data(
    session_id: str = Path(..., description="session ID to retrieve"),
    date: Optional[str] = Query(None, description="Optional date hint (2015-06-11) to narrow search")
):
    """
    retrieve and compress session data into a base64 encoded string.
    
    - **session_id**: session ID to retrieve
    - **date**: optional date hint in the format '2025-06-11' to narrow down the search
    
    Returns: A base64 encoded string containing compressed session data
    """
    try:
        return data_manager.encode(session_id, date)
    except Exception as e:
        logger.error(f"Error retrieving session data for {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")