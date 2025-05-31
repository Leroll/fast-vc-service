from fastapi import FastAPI
import uvicorn
from loguru import logger
from pydantic import BaseModel
import traceback

from routers import base_router, websocket_router
from logging_config import LoggingSetup
from realtime_vc import RealtimeVoiceConversion, RealtimeVoiceConversionConfig


class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8042

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Initialize logging
    LoggingSetup.setup()
    logger.info("-" * 42)
    logger.info("initializing Fast Voice Conversion Service...")
    
    # Create FastAPI application
    app = FastAPI(
        title="Fast Voice Conversion Service",
        description="Voice Conversion Service API"
    )
    
    # Initialize realtime voice conversion service
    logger.info("loading Realtime Voice Conversion...")
    try:
        app.state.realtime_vc = RealtimeVoiceConversion(
            RealtimeVoiceConversionConfig()
        )
    except Exception as e:
        logger.error(f"faild to initialize Realtime Voice Conversion: {traceback.format_exc()}")
        raise
    
    # Include routers
    logger.info("registering routers...")
    app.include_router(base_router)
    app.include_router(websocket_router)
    
    logger.success("Successfully initialized Fast Voice Conversion Service")
    logger.info("-" * 42)
    return app
    
if __name__ == "__main__":
    # Run the application with Uvicorn
    app_config = AppConfig()
    app = create_app()
    uvicorn.run(
        app,
        host=app_config.host,
        port=app_config.port,
        log_config=None  # Forbid default logging config
    )