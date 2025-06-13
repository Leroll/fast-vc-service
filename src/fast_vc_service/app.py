from fastapi import FastAPI
import uvicorn
from loguru import logger
from pydantic import BaseModel
import traceback

from fast_vc_service.config import Config
from fast_vc_service.routers import base_router, websocket_router, tools_router
from fast_vc_service.logging_config import LoggingSetup
from fast_vc_service.realtime_vc import RealtimeVoiceConversion
from fast_vc_service.tools.session_data_manager import SessionDataManager

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Initialize logging
    cfg = Config().get_config()
    LoggingSetup.setup(cfg.app.log_dir)
    logger.info("-" * 21 + "initilizing service" + "-" * 21)
    
    # Create FastAPI application
    app = FastAPI(
        title="Realtime Voice Conversion Service",
        description="Voice Conversion Service API"
    )
    
    # Initialize realtime voice conversion service
    app.state.cfg = cfg
    
    logger.info("initializing SessionDataManager...")
    app.state.session_data_manager = SessionDataManager(
        outputs_dir=cfg.realtime_vc.save_dir
    )
    
    logger.info("initializing class: RealtimeVoiceConversion ...")
    try:
        app.state.realtime_vc = RealtimeVoiceConversion(
            cfg.realtime_vc,
            cfg.models,
        )
    except Exception as e:
        logger.error(f"faild to initialize RealtimeVoiceConversion: {traceback.format_exc()}")
        raise
    
    # Include routers
    logger.info("registering routers...")
    app.include_router(base_router)
    app.include_router(websocket_router)
    app.include_router(tools_router)
    
    logger.info("-" * 21 + "service initialized" + "-" * 21)
    return app

def main() -> None:
    """Main function to run the FastAPI application."""
    app_config = Config().get_config().app
    logger.info(f"Starting fast vc service on {app_config.host}:{app_config.port}")
    logger.info(f"Number of workers: {app_config.workers}")
    
    uvicorn.run(
        "fast_vc_service.app:create_app",
        host=app_config.host,
        port=app_config.port,
        workers=app_config.workers,
        factory=True,
        log_config=None  # Forbid default logging config
    )
    
if __name__ == "__main__":
    main()