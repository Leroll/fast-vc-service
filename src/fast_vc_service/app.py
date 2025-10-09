from fastapi import FastAPI
import uvicorn
import os
from loguru import logger
from pydantic import BaseModel
import traceback
import multiprocessing

from fast_vc_service.config import Config
from fast_vc_service.routers import base_router, websocket_router, tools_router
from fast_vc_service.logging_config import LoggingSetup
from fast_vc_service.realtime_vc import RealtimeVoiceConversion
from fast_vc_service.tools.session_data_manager import SessionDataManager

def _get_work_id() -> str:
    """获取当前worker的index，从1开始的计数
    
    在多卡部署多实例的场景下，会使用该 wid
    """
    process_name = multiprocessing.current_process().name
    logger.info(f"process_name: {process_name}")
    if "SpawnProcess" in process_name:
        wid = int(process_name.split('-')[-1])
        return wid
    
    # pid 兜底
    wid = os.getpid()
    logger.info(f"faild to get wid, use pid instead. process_name:{process_name}, pid: {wid}")
    return str(wid)
    
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Initialize logging
    cfg = Config().get_config()
    worker_id = _get_work_id()
    LoggingSetup.setup(cfg.app.log_dir, worker_pid=worker_id)
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
        search_dir=cfg.realtime_vc.save_dir
    )
    
    logger.info("initializing class: RealtimeVoiceConversion ...")
    try:
        cfg.realtime_vc.device = cfg.realtime_vc.device[ (int(worker_id)-1) % len(cfg.realtime_vc.device) ]
        
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