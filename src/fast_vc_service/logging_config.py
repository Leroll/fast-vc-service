from loguru import logger
import logging
import sys 
from pathlib import Path
import os
import socket

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
    def _get_instance_identifier(cls) -> str:
        """获取实例标识符，用于区分不同的实例"""
        # 优先级顺序：环境变量 > Pod名 > 主机名 > 默认值
        
        # 1. 使用自定义环境变量
        instance_id = os.getenv("INSTANCE_ID")
        if instance_id:
            return instance_id
            
        # 2. 使用Kubernetes Pod名称
        pod_name = os.getenv("HOSTNAME")  # K8s中通常Pod名就是HOSTNAME
        if pod_name and pod_name != "localhost":
            return pod_name
            
        # 3. 使用主机名
        try:
            hostname = socket.gethostname()
            if hostname and hostname != "localhost":
                return hostname
        except Exception:
            pass
            
        # 4. 默认值
        return "default"
    
    @classmethod
    def setup(cls, log_dir: str, instance_name: str = None, worker_pid: int = None):
        """配置日志系统，确保只被调用一次
        
        Args:
            log_dir: 日志目录
            instance_name: 实例名称，如果不提供则自动获取
            worker_pid: Worker进程ID，如果不提供则自动获取
        """
        
        # 如果已经初始化过，直接返回
        if cls._initialized:
            logger.debug("logging system already initialized, skipping setup")
            return
            
        # 获取实例标识符
        if instance_name is None:
            instance_name = cls._get_instance_identifier()
            
        # 获取worker PID
        if worker_pid is None:
            worker_pid = os.getpid()
            
        # 移除默认的 loguru 处理器
        logger.remove()
        
        # 添加控制台输出
        logger.add(
            sys.stdout,
            level="INFO",
            format=f"<bold><green>{{time:YYYY-MM-DD HH:mm:ss.SSS}}</green></bold> | <bold><level>{{level}}</level></bold> | <bold><magenta>{{name}}</magenta></bold> | <bold><cyan>{worker_pid}</cyan></bold> | <bold><white>{{message}}</white></bold>",
            colorize=True,
        )
        
        log_dir = Path(log_dir)
        logger.info(f"logging directory: {log_dir}, instance: {instance_name}, worker PID: {worker_pid}")
        
        # 添加 Uvicorn 日志文件 - 包含实例名
        logger.add(
            str(log_dir / f"uvicorn-{instance_name}.log"),
            rotation="5 MB",
            level="INFO",
            enqueue=True,
            backtrace=True,
            encoding="utf-8",
            filter=lambda record: "uvicorn" in record["name"],
            format=f"{{time:YYYY-MM-DD HH:mm:ss.SSS}} | {{level}} | {{name}} | {worker_pid} | {{message}}",
        )
        
        # 添加应用日志文件 - 包含实例名
        logger.add(
            str(log_dir / f"app-{instance_name}.log"),
            rotation="5 MB", 
            level="INFO",
            enqueue=True,
            backtrace=True,
            encoding="utf-8",
            filter=lambda record: "uvicorn" not in record["name"],
            format=f"{{time:YYYY-MM-DD HH:mm:ss.SSS}} | {{level}} | {{name}} | {worker_pid} | {{message}}",
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
        logger.info(f"logging system initialized successfully for instance: {instance_name}, worker PID: {worker_pid}")
