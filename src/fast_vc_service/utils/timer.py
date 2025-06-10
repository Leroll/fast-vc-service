import time
from loguru import logger

def timer_decorator(func):
    """装饰器，用于计算函数的运行时间"""
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        logger.info(f"{func.__name__} cost: {execution_time:0.3f} s")
        return result
    return wrapper


if __name__ == "__main__":
    # test
    
    @timer_decorator
    def example_function():
        time.sleep(2)
        
    example_function()