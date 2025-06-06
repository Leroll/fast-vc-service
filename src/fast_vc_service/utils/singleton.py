class Singleton:
    """单例模式
    """
    def __init__(self, cls):
        self._cls = cls
        self._instance = {}
    
    def __call__(self, *args, **kargs):
        if self._cls not in self._instance:
            self._instance[self._cls] = self._cls(*args, **kargs)
        return self._instance[self._cls]