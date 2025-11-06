from dotenv import load_dotenv
load_dotenv()
import yaml
import os
from pydantic import BaseModel
from enum import Enum
import uuid
from loguru import logger
from pathlib import Path
import traceback
import torch
from typing import Literal


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
    device: list = ["cuda" if torch.cuda.is_available() else "cpu"]  # 支持多卡，比如 ["cuda:0", "cuda:1"]
                                                                     # 在多卡场景下，worker会循环依次部署到各个卡上
    is_debug: bool = False  # 是否启用调试模式，调试模式会保存更多中间文件，便于排查问题
    
    # wav 相关
    reference_wav_path: str = "wavs/references/ref-24k.wav"
    save_dir: str = "outputs/"  # save
    save_input: bool = True  # is to save input wav
    save_output: bool = True  # is to save output wav
    
    # realtime 
    SAMPLERATE_IN: int = 16000  # RealtimeVC模块输入采样率，从输入 到 vad, rmvpe, content encoder 都是16k
    SAMPLERATE_OUT: int = 22050  # vc模型输出采样率，一直延续到 Realtime_VC 模块的输出，会经过 rms-mixing 和 sola 
    BIT_DEPTH: int = 16  # 音频流的位深度，16位
    FRAMERATE: int = 50  # 帧率，代表系统的精度，和 content encoder的帧率一致； 1s 50帧，每帧20ms
                         # rvc:100（与其内部的f0 model一致）, seed-vc: 50（和content encoder一致）   
    
    # 上下文             
    extra_time_ce: float = 4.5   # 留给 content encoder 上文额外时间，默认2.5s
    extra_time_dit: float = 1.5  # 留给 dit 上文额外时间，默认0.5s, 包含在extra_time_ce中，需要满足 extra_time_dit < extra_time_ce，
                                 # content encoder 在得到 feat 后，会减去相对dit多出来的部分，再输入给 dit
    sola_buffer_time: float = 0.04  # sola算法做crossfade的区域，默认：0.04，不要超过 0.08; 会增加整体延迟
    block_time: float = 0.5  # 每块的时长，默认 0.5
    extra_time_right: float = 0.02  # 结尾的额外时间，默认: 0.02, 会增加整体延迟
    
    # auto_f0 
    is_f0: bool =  True  # 是否使用自适应音高
    total_block_for_f0: int = 6  # 6； 用于计算中位数音高的总块数，只有探测到人声的才会包含，6块对应 3s
    
    # vc models
    diffusion_steps: int = 10  # 10；                    
    inference_cfg_rate: float = 0.7  # 0.7
    max_prompt_length: float = 3.0 # 3； 
    
    # rms_mix
    rms_mix_rate: float = 0    # 0.25； 这个参数是用来控制 RMS 混合的比例，
                               # 范围是 0 到 1。
                               # 0 表示完全使用 Input 的包络，1 表示完全使用 Infer 包络。
                               
    # sola
    is_sola: bool = True  # 是否启用 SOLA 算法进行时域拼接  
                                        
    # SLOW 参数, 包-包之间延迟认定为SLOW的阈值
    send_slow_threshold: int = 100  # 100ms, 两个客户段发送过来的音频包之间的间隔，认定SLOW的阈值
                                    # 一般客户端发送过来的音频包间隔是 20ms 或者 10ms
    recv_slow_threshold: int = 700  # 700ms，两个客户段收到服务端发送回去的音频包之间的时间间隔，认定SLOW的阈值
                                    # 服务端发送回去的包，即 block_time，默认是500ms，所以超过700ms认为是SLOW
    vc_slow_threshold: int = 300  # 从累计到一个chunk开始，到完成vc并推送给客户段之间的耗时
                                  # 500ms一个chunk的话，认为vc时间超过300就算SLOW
    
    def model_post_init(self, context):
        
        super().model_post_init(context)
        assert self.SAMPLERATE_IN % self.FRAMERATE == 0, "SAMPLERATE_IN must be divisible by FRAMERATE"
        assert self.SAMPLERATE_OUT % self.FRAMERATE == 0, "SAMPLERATE_OUT must be divisible by FRAMERATE"
        assert self.extra_time_ce > self.extra_time_dit, "extra_time_ce must be greater than extra_time_dit"
        assert self.sola_buffer_time <= 0.08, "sola_buffer_time must be less than or equal to 0.08s"


class ModelConfig(BaseModel):
    """model config"""
    is_torch_compile: bool = False  # use torch.compile to accelerate
    
    # retrieval
    is_retrieval: bool = False  # 是否启用语义特征检索模块
    index_rate: float = 1.0  ## 检索特征相对权重，0.0 表示不使用检索特征，1.0 表示完全使用检索特征
    index_path: str | None = None  # faiss索引文件路径
    
    # vad
    speech_noise_thres: float = 0.8  # VAD  语音与噪声能量比阈值 控制噪声过滤的灵敏度。vad默认0.6
    decibel_thres: float = -50.0  # 分贝阈值 低于该分贝的帧判为静音。vad默认-100.0
    
    # cfm
    t_span_schedule: Literal["linear", "cosine"] = "cosine"  # 线性 or 余弦重排
    
    # 自定义模型路径，比如训练后的模型
    dit_checkpoint_path: str | None = None
    dit_config_path: str | None = None

    defalut_original_model: str = "tiny"  # "tiny", "small", "base"  
                                          # 如果没有指定自定义的模型路径：dit_checkpoint_path， dit_config_path。
                                          # 则使用seed-vc原始模型


class ConfigData(BaseModel):
    app: AppConfig = AppConfig()
    buffer: BufferConfig = BufferConfig()
    realtime_vc: RealtimeVoiceConversionConfig = RealtimeVoiceConversionConfig()
    models: ModelConfig = ModelConfig()


@Singleton
class Config(object):
    def __init__(self, config_path: str = None):
        """
        初始化配置
        
        Args:
            config_path: 配置文件路径，如果为None则从环境变量CONFIG_PATH获取，
                        如果环境变量也没有则使用默认配置
        """
        self.config_path = config_path or os.getenv("CONFIG_PATH")
        self.config = self._load_config()
        self.config_id = str(uuid.uuid4().hex)
        logger.info(f"Config ID: {self.config_id}")
        if self.config_path:
            logger.info(f"Loaded config from: {self.config_path}")
        else:
            logger.info("Using default configuration")

    def _load_config(self) -> ConfigData:
        """加载配置文件"""
        if not self.config_path:
            logger.info("No config path specified, using default values")
            return ConfigData()
            
        config_path = Path(self.config_path)
        
        try:
            if not config_path.exists():
                logger.warning(f"Config file {config_path} not found, using default values")
                return ConfigData()
                
            config_dict = self._yaml_load(config_path)
            config = ConfigData(**config_dict)
            logger.info(f"Successfully loaded config from {config_path}")
            return config
            
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in {config_path}: {e}, using default values")
            return ConfigData()
        except Exception as e:
            logger.error(f"Unexpected error loading config from {config_path}, using default values:\n{traceback.format_exc()}")
            return ConfigData()

    def _yaml_load(self, path: Path):
        """加载YAML文件"""
        with open(path, "r", encoding="utf-8") as fin:
            return yaml.safe_load(fin)

    def get_config(self) -> ConfigData:
        """获取配置对象"""
        return self.config


if __name__ == "__main__":
    # 测试不同的配置加载方式
    print("=== Testing config loading ===")
    
    # 1. 默认方式（无配置文件）
    cfg1 = Config()
    print(f"Default config ID: {cfg1.config_id}")
    
    # 2. 指定配置文件
    cfg2 = Config("configs/prod.yaml")
    print(f"Specific file config ID: {cfg2.config_id}")
    
    # 3. 测试单例模式
    cfg3 = Config()
    cfg4 = Config()
    print(f"Singleton test - cfg3 ID: {cfg3.config_id}, cfg4 ID: {cfg4.config_id}")
    print(f"Are they the same instance? {cfg3 is cfg4}")


