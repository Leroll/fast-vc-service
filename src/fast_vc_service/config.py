import yaml
import os
from pydantic import BaseModel
from enum import Enum
import uuid
from loguru import logger
from pathlib import Path
import traceback
import torch
from dotenv import load_dotenv
load_dotenv()

from fast_vc_service.utils import Singleton  


class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8042
    workers: int = 2  # Number of workers for uvicorn
    receive_timeout: int = 60*8  # Timeout for receiving audio bytes in seconds
    log_dir: str = "logs"
    
class BufferConfig(BaseModel):
    prefill_time: int = 375  # Prefill time in milliseconds
    opus_frame_duration: int = 20  # Opus frame duration in milliseconds
    
class RealtimeVoiceConversionConfig(BaseModel):
    """语音转换服务配置类"""
    
    # 设备
    device: str = str(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    
    # wav 相关
    reference_wav_path: str = "wavs/references/ref-24k.wav"
    save_dir: str = "outputs/"  # save
    save_input: bool = True  # is to save input wav
    save_output: bool = True  # is to save output wav
    
    # realtime 
    SAMPLERATE: int = 16_000  # also called common_sr
                                # 音频流在vc过程中基础采样率
                                # 不可修改，需要保证为 16k，vad，senmantic 都是 16k 模型
                                # 某些环节采样率会改变，比如dit model会更改为22050，需要再次转换回来
                                # rmvpe 也需要 16000
    BIT_DEPTH: int = 16  # 音频流的位深度，16位
    
    zc_framerate: int = 50  # zc = samplerate // zc_framerate, rvc:100, seed-vc: 50
    block_time: float = 0.5  # 0.5 ；这里的 block time 是 0.5s                    
    crossfade_time: float = 0.04  # 0.04 ；用于平滑过渡的交叉渐变长度，这里设定为 0.04 秒。交叉渐变通常用于避免声音中断或“断层”现象。
    extra_time: float = 2.5  # 2.5；  附加时间，设置为 0.5秒。可能用于在处理音频时延长或平滑过渡的时间。
                             # 原本默认0.5，后面更新成2.5了，放在音频的前面
    extra_time_right: float = 0.02  # 0.02；
    
    # auto_f0 
    is_f0: bool =  True  # 是否使用自适应音高
    total_block_for_f0: int = 6  # 6； 用于计算中位数音高的总块数，只有探测到人声的才会包含，6块对应 3s

    # noise_gata
    noise_gate: bool = True  # 是否使用噪声门
    noise_gate_threshold: float = -60  # 噪声门的阈值，单位是分贝，-60dB
    
    # vc models
    diffusion_steps: int = 10  # 10；                    
    inference_cfg_rate: float = 0.7  # 0.7
    max_prompt_length: float = 3.0 # 3； 
    ce_dit_difference: float = 2  # 2 seconds， content encoder ?
    
    # rms_mix
    rms_mix_rate: float = 0    # 0.25； 这个参数是用来控制 RMS 混合的比例，
                               # 范围是 0 到 1。
                               # 0 表示完全使用 Input 的包络，1 表示完全使用 Infer 包络。
                               
    # 辅助参数
    max_tracking_counter: int = 10_000  # 用于记录单chunk推理时间损耗的最大记录数量
                                        # record audio duration = max_tracking_counter * block_time
                                        # default: 10_000 * 0.5 = 5000s = 83min
                                        
    # SLOW 参数, 包-包之间延迟认定为SLOW的阈值
    send_slow_threshold: int = 100  # 100ms, 两个客户段发送过来的音频包之间的间隔，认定SLOW的阈值
                                    # 一般客户端发送过来的音频包间隔是 20ms 或者 10ms
    recv_slow_threshold: int = 700  # 700ms，两个客户段收到服务端发送回去的音频包之间的时间间隔，认定SLOW的阈值
                                    # 服务端发送回去的包，即 block_time，默认是500ms，所以超过700ms认为是SLOW
    vc_slow_threshold: int = 300  # 从累计到一个chunk开始，到完成vc并推送给客户段之间的耗时
                                  # 500ms一个chunk的话，认为vc时间超过300就算SLOW


class ModelConfig(BaseModel):
    """model config"""
    device: str = "cuda"
    is_torch_compile: bool = False  # use torch.compile to accelerate
    
    # dit model
    dit_repo_id: str = "Plachta/Seed-VC"
    
    # tiny version
    dit_model_filename: str = "DiT_uvit_tat_xlsr_ema.pth"  
    dit_config_filename: str = "config_dit_mel_seed_uvit_xlsr_tiny.yml"  
    
    # small version
    # dit_model_filename: str = "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth"  
    # dit_config_filename: str = "config_dit_mel_seed_uvit_whisper_small_wavenet.yml"
    
    # base version
    # dit_model_filename: str = "DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned.pth"  
    # dit_config_filename: str = "config_dit_mel_seed_uvit_whisper_base_f0_44k.yml"


class ConfigData(BaseModel):
    app: AppConfig = AppConfig()
    buffer: BufferConfig = BufferConfig()
    realtime_vc: RealtimeVoiceConversionConfig = RealtimeVoiceConversionConfig()
    models: ModelConfig = ModelConfig()


@Singleton
class Config(object):
    def __init__(self, conf_dir : Path = 'configs'):
        self.env_profile = self.__get_env_profile()
        self.config = self.__init_config(conf_dir)
        self.config_id = str(uuid.uuid4().hex)
        logger.info(f"Config ID: {self.config_id}")

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
    cfg = Config()
    cfg_id, cfg = cfg.config_id, cfg.get_config()
    logger.info(f"Config ID: {cfg_id} \n, Configuration: {cfg}")
    logger.info('-'*42)
    cfg_id_1 = Config().config_id
    cfg_id_2 = Config().config_id
    logger.info(f"Config ID 1: {cfg_id_1}")
    logger.info(f"Config ID 2: {cfg_id_2}")
    
    
    