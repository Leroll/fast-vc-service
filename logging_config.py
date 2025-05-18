from loguru import logger
import logging
import sys
import os   

class InterceptHandler(logging.Handler):
    """将标准 logging 日志转发到 Loguru"""
    
    def emit(self, record: logging.LogRecord) -> None:
        """将日志记录转发到 Loguru
        """
    
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # 查找调用者
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(
            depth=depth,
            exception=record.exc_info
        ).log(level, record.getMessage()) 
        
def setup_logging():
    """配置日志系统"""
    
    # 移除默认的 loguru 处理器
    logger.remove()
    
    # 添加控制台输出
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    
    # 添加 Uvicorn 日志文件
    logger.add(
        "logs/uvicorn.log",
        rotation="1 MB",
        level="INFO",
        enqueue=True,
        backtrace=True,
        encoding="utf-8",
        filter=lambda record: "uvicorn" in record["name"],
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name} | {function}:{line} | {message}",
    )
    
    # 添加 app 日志文件 
    def log_filter(record):
        """过滤器函数，只记录bind了app的日志
        
        暂时还未启用
        app_logger = logger.bind(name="app")
        """
        flag = record['extra'].get("name", None) == "app"
        return flag
    
    logger.add(
        "logs/app.log",
        rotation="1 MB", 
        level="INFO",
        enqueue=True,
        backtrace=True,
        encoding="utf-8",
        filter=lambda record: "uvicorn" not in record["name"],
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name} | {function}:{line} | {message}",
    )
    
    # 配置标准日志库将日志发送到我们的拦截器
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # 获取所有的日志记录器并应用配置
    for logger_name in logging.root.manager.loggerDict:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]
        logging_logger.propagate = False
        logging_logger.level = logging.INFO

