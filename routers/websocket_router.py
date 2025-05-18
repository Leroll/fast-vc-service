from fastapi import APIRouter, WebSocket
from loguru import logger

websocket_router = APIRouter()

@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received data: {data}")
            await websocket.send_text(f"Message text was: {data}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()
        logger.info("WebSocket connection closed")
    
    
    