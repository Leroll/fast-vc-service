from loguru import logger
import logging
import sys 

class InterceptHandler(logging.Handler):
    """send standard logging messages to Loguru logger"""
    
    def emit(self, record: logging.LogRecord) -> None:
        """send a log record to Loguru logger
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

class LoggingSetup:
    """日志配置类，使用单例模式确保只初始化一次"""
    
    # 类变量，用于追踪是否已初始化
    _initialized = False
    
    @classmethod
    def setup(cls):
        """配置日志系统，确保只被调用一次"""
        
        # 如果已经初始化过，直接返回
        if cls._initialized:
            logger.debug("logging system already initialized, skipping setup")
            return
            
        # 移除默认的 loguru 处理器
        logger.remove()
        
        # 添加控制台输出
        logger.add(
            sys.stdout,
            level="INFO",
            format="<bold><green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green></bold> | <bold><level>{level}</level></bold> | <bold><magenta>{name}</magenta></bold> | <bold><white>{message}</white></bold>",
            colorize=True,
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
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name} | {message}",
        )
        
        logger.add(
            "logs/app.log",
            rotation="1 MB", 
            level="INFO",
            enqueue=True,
            backtrace=True,
            encoding="utf-8",
            filter=lambda record: "uvicorn" not in record["name"],
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name} | {message}",
        )
        
        # 配置标准日志库将日志发送到我们的拦截器
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
        
        # 获取所有的日志记录器并应用配置
        for logger_name in logging.root.manager.loggerDict:
            logging_logger = logging.getLogger(logger_name)
            logging_logger.handlers = [InterceptHandler()]
            logging_logger.propagate = False
            logging_logger.level = logging.INFO
        
        # 标记为已初始化
        cls._initialized = True
        logger.info("logging system initialized successfully")
