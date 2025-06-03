import yaml
import os
from pydantic import BaseModel
from enum import Enum

from fast_vc_service.utils import Singleton  
from fast_vc_service.app import AppConfig
from fast_vc_service.realtime_vc import RealtimeVoiceConversionConfig
from fast_vc_service.models import ModelConfig

class ConfigData(BaseModel):
    version: str = "0.0.0.1"
    app: AppConfig = AppConfig()
    realtime_vc: RealtimeVoiceConversionConfig = RealtimeVoiceConversionConfig()
    models: ModelConfig = ModelConfig()


@Singleton
class Config(object):
    def __init__(self, conf_path='config'):
        self.env = self.__init_env()
        self.config = self.__init_config(conf_path)

    def yaml_load(self, path):
        with open(path, "r", encoding="utf-8") as fin:
            return yaml.load(fin, Loader=yaml.FullLoader)

    def __init_env(self) -> str:
        env = os.getenv("env_profile", "prod")
        print(f"Env is {env}")
        return env

    def __init_config(self, conf_path: str) -> ConfigData:
        """从环境变量 env_profile 中获取环境名称并加载配置

        Args:
            conf_path (str): 配置文件夹路径

        Returns:
            ConfigData: Pydantic 验证后的配置对象
        """
        config_path = f'{conf_path}/{self.env}.yaml'
        try:
            config_dict = self.yaml_load(config_path)
            config = ConfigData(**config_dict)
        except FileNotFoundError:
            print(f"Config file {config_path} not found, using default values")
            config = ConfigData()
        return config

    def get_config(self):
        return self.config


# 初始化配置
cfg = Config('./config').get_config()

if __name__ == "__main__":
    cfg = Config('./config')
    print(cfg.env)
    
    cfg = cfg.get_config()
    print(cfg)