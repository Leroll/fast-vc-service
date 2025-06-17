from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as FPath  # to avoid conflict with Path from pathlib
from loguru import logger
from typing import Optional

tools_router = APIRouter(tags=["Tools"], prefix="/tools")

@tools_router.get("/session/{session_id}", summary="Retrieve compressed session data")
async def get_session_data(
    request: Request,
    session_id: str = FPath(..., description="session ID to retrieve"),
    date: Optional[str] = Query(None, description="Optional date hint (2015-06-11) to narrow search")
):
    """
    retrieve and compress session data into a base64 encoded string.
    
    - **session_id**: session ID to retrieve
    - **date**: optional date hint in the format '2025-06-11' to narrow down the search
    
    Returns: A base64 encoded string containing compressed session data
    
    Example:
    ```
    curl -X GET "http://localhost:8042/tools/session/client0_5ad8c298" > outputs/encoded.txt
    curl -X GET "http://localhost:8042/tools/session/client0_5ad8c298?date=2025-06-11" > outputs/encoded.txt
    ```
    """
    try:
        data_manager = request.app.state.session_data_manager
        return data_manager.encode(session_id, date)
    except Exception as e:
        logger.error(f"Error retrieving session data for {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@tools_router.get("/performance-report", summary="Get current realtime voice conversion performance report")
async def get_performance_report(request: Request):
    """
    Get current performance statistics for the realtime voice conversion system.
    
    Returns detailed timing statistics for all voice conversion modules including:
    - VAD processing time
    - Noise gate processing time  
    - Preprocessing time
    - Semantic extraction time
    - Diffusion model time
    - Vocoder time
    - RMS mixing time
    - SOLA algorithm time
    - Overall chunk processing time
    
    Example:
    ```
    curl -X GET "http://localhost:8042/tools/performance-report"
    ```
    """
    try:
        # Get the realtime VC instance from app state
        if not hasattr(request.app.state, 'realtime_vc'):
            raise HTTPException(status_code=404, detail="Realtime voice conversion service not initialized")
        
        realtime_vc = request.app.state.realtime_vc
        return realtime_vc._performance_report()
        
    except Exception as e:
        logger.error(f"Error retrieving performance report: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

