from fastapi import FastAPI
import uvicorn
from loguru import logger
from pydantic import BaseModel

from routers import base_router, websocket_router
from logging_config import LoggingSetup
from realtime_vc import RealtimeVoiceConversion, RealtimeVoiceConversionConfig

class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8042

# Initialize logging
LoggingSetup.setup()  

# Initialize the RealtimeVoiceConversion instance
realtime_vc_cfg = RealtimeVoiceConversionConfig()
realtime_vc = RealtimeVoiceConversion(realtime_vc_cfg)
logger.info(f"RealtimeVoiceConversion initialized, instance_id: {realtime_vc.instance_id}")

# Create FastAPI application
app = FastAPI(
    title="Fast Voice Conversion Service",
    description="Voice Conversion Service API"
)
app.state.realtime_vc = realtime_vc  # Store the instance in the app state
app.include_router(base_router)  # Include routers
app.include_router(websocket_router)
    
if __name__ == "__main__":
    # Run the application with Uvicorn
    app_config = AppConfig()
    uvicorn.run(
        app,
        host=app_config.host,
        port=app_config.port,
        log_config=None  # Forbid default logging config
    )