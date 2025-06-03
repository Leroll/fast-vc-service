from fastapi import FastAPI
import uvicorn
from loguru import logger
from pydantic import BaseModel
import traceback

from fast_vc_service.routers import base_router, websocket_router
from fast_vc_service.logging_config import LoggingSetup
from fast_vc_service.realtime_vc import RealtimeVoiceConversion, RealtimeVoiceConversionConfig


class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8042

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Initialize logging
    LoggingSetup.setup()
    logger.info("-" * 21 + "initilizing service" + "-" * 21)
    
    # Create FastAPI application
    app = FastAPI(
        title="Realtime Voice Conversion Service",
        description="Voice Conversion Service API"
    )
    
    # Initialize realtime voice conversion service
    logger.info("initializing class: RealtimeVoiceConversion ...")
    try:
        app.state.realtime_vc = RealtimeVoiceConversion(
            RealtimeVoiceConversionConfig()
        )
    except Exception as e:
        logger.error(f"faild to initialize RealtimeVoiceConversion: {traceback.format_exc()}")
        raise
    
    # Include routers
    logger.info("registering routers...")
    app.include_router(base_router)
    app.include_router(websocket_router)
    
    logger.info("-" * 21 + "service initialized" + "-" * 21)
    return app

def main(host: str = "0.0.0.0", port: int = 8042) -> None:
    """Main function to run the FastAPI application."""
    app_config = AppConfig(host=host, port=port)
    app = create_app()
    uvicorn.run(
        app,
        host=app_config.host,
        port=app_config.port,
        log_config=None  # Forbid default logging config
    )
    
if __name__ == "__main__":
    main()