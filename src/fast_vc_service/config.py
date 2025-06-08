import yaml
import os
from pydantic import BaseModel
from enum import Enum
import uuid
from loguru import logger
from pathlib import Path
import traceback
from dotenv import load_dotenv
load_dotenv()

from fast_vc_service.utils import Singleton  
from fast_vc_service.app import AppConfig
from fast_vc_service.realtime_vc import RealtimeVoiceConversionConfig
from fast_vc_service.models import ModelConfig

class ConfigData(BaseModel):
    app: AppConfig = AppConfig()
    realtime_vc: RealtimeVoiceConversionConfig = RealtimeVoiceConversionConfig()
    models: ModelConfig = ModelConfig()


@Singleton
class Config(object):
    def __init__(self, conf_dir : Path = 'configs'):
        self.env_profile = self.__get_env_profile()
        self.config = self.__init_config(conf_dir)
        self.config_id = str(uuid.uuid4().hex)

    def yaml_load(self, path):
        with open(path, "r", encoding="utf-8") as fin:
            return yaml.safe_load(fin)

    def __get_env_profile(self) -> str:
        env_profile = os.getenv("env_profile", "prod")
        logger.info(f"Environment profile: {env_profile}")
        return env_profile

    def __init_config(self, conf_dir: Path) -> ConfigData:
        """从环境变量 env_profile 中获取环境名称并加载配置

        Args:
            conf_path (str): 配置文件夹路径

        Returns:
            ConfigData: Pydantic 验证后的配置对象
        """
        config_path = Path(conf_dir) / f"{self.env_profile}.yaml"
        try:
            config_dict = self.yaml_load(config_path)
            config = ConfigData(**config_dict)
        except FileNotFoundError:
            logger.error(f"Config file {config_path} not found, using default values")
            config = ConfigData()
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}, using default values")
            config = ConfigData()
        except Exception as e:
            logger.error(f"Unexpected error loading config, using default values:\n{traceback.format_exc()}")
            config = ConfigData()
        return config

    def get_config(self):
        return self.config

if __name__ == "__main__":
    cfg = Config('./configs')
    cfg_id, cfg = cfg.config_id, cfg.get_config()
    logger.info(f"Config ID: {cfg_id} \n, Configuration: {cfg}")
    logger.info('-'*42)
    cfg_id_1 = Config('./configs').config_id
    cfg_id_2 = Config('./configs').config_id
    logger.info(f"Config ID 1: {cfg_id_1}")
    logger.info(f"Config ID 2: {cfg_id_2}")
    
    
    