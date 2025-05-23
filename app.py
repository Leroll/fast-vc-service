from fastapi import FastAPI
from routers.base_router import base_router
from routers.websocket_router import websocket_router
from logging_config import LoggingSetup
import uvicorn

LoggingSetup.setup()  # solve uviron loguru conflict

# Create FastAPI application
app = FastAPI(
    title="Fast Voice Conversion Service",
    description="Voice Conversion Service API"
)

# Include routers
app.include_router(base_router)
app.include_router(websocket_router)
    
# 启动服务 
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8042,
        log_config=None  # 禁用 Uvicorn 自有日志配置
    )