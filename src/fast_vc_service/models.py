from dotenv import load_dotenv
load_dotenv()

import yaml
import torch
from loguru import logger
from pydantic import BaseModel
import sys
from pathlib import Path
import os
from huggingface_hub import hf_hub_download

# add seed-vc path to sys.path
SEED_VC_PATH = Path(__file__).resolve().parent.parent.parent / "externals" / "seed_vc"
if str(SEED_VC_PATH) not in sys.path:
    sys.path.append(str(SEED_VC_PATH))
from externals.seed_vc.modules.commons import (
    recursive_munch, load_checkpoint, build_model
)

# import custom modules
from fast_vc_service.utils import timer_decorator
from fast_vc_service.config import ModelConfig


def load_custom_model_from_hf(repo_id, model_filename="pytorch_model.bin", config_filename="config.yml"):
    """
    根据.env中配置的HF_HUB_CACHE路径下载模型和配置文件
    """ 
    model_path = hf_hub_download(repo_id=repo_id, filename=model_filename)
    if config_filename is None:
        return model_path
    config_path = hf_hub_download(repo_id=repo_id, filename=config_filename)

    return model_path, config_path


class ModelFactory:
    
    def __init__(self,model_config:ModelConfig=ModelConfig(), is_f0=False):
        """model factory, all models are loaded here"""
        self.logger = logger.bind(name="app")
        self.logger.info("initializing ModelFactory...")
        self.cfg = model_config
        self.is_f0 = is_f0
        self.hf_cache_path, self.modelscope_cache_path = self._setup_cache_paths()
        self.device = self.cfg.device
        self.is_torch_compile = self.cfg.is_torch_compile
        self.logger.info(f"HF_ENDPOINT: {os.environ.get('HF_ENDPOINT', 'default')}")
        self.logger.info(f"Using device: {self.device}")
        self.logger.info(f"Using torch compile: {self.is_torch_compile}")
        
        self.models = self._load_models()

    def _setup_cache_paths(self):
        """set up cache paths for HF and ModelScope"""
        project_root = Path(__file__).resolve().parent.parent.parent
        
        hf_hub_cache = os.environ.get('HF_HUB_CACHE', 'checkpoints/hf_cache')
        modelscope_cache = os.environ.get('MODELSCOPE_CACHE', 'checkpoints/modelscope_cache')
        
        hf_hub_cache = Path(hf_hub_cache)
        modelscope_cache = Path(modelscope_cache)
        
        if not hf_hub_cache.is_absolute():
            hf_hub_cache = project_root / hf_hub_cache
        if not modelscope_cache.is_absolute():
            modelscope_cache = project_root / modelscope_cache
        
        # set absolute paths to environment variables
        os.environ['HF_HUB_CACHE'] = str(hf_hub_cache)
        os.environ['MODELSCOPE_CACHE'] = str(modelscope_cache)
        
        hf_hub_cache.mkdir(parents=True, exist_ok=True)
        modelscope_cache.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"HF_HUB_CACHE set to: {hf_hub_cache}")
        self.logger.info(f"MODELSCOPE_CACHE set to: {modelscope_cache}")
        
        return hf_hub_cache, modelscope_cache

    @timer_decorator
    def _load_models(self):
        """加载各种模型"""
        self.dit_model, self.dit_fn, self.dit_config, self.model_params, self.sr  = self._load_dit_model()
        self.campplus_model = self._load_campplus_model()
        self.vocoder_fn = self._load_vocoder_fn()
        self.semantic_fn = self._load_semantic_fn() 
        self.to_mel, self.mel_fn_args = self._load_mel()
        self.vad_model = self._load_vad_model()
        self.f0_fn = self._load_f0_fn() if self.is_f0 else None
        
        if self.is_torch_compile:  # if using torch compile to accelerate
            self._torch_compile()
        
        models = {
            # main models
            "campplus_model": self.campplus_model,
            "dit_model": self.dit_model,
            
            "semantic_fn": self.semantic_fn,
            "dit_fn": self.dit_fn,
            "vocoder_fn": self.vocoder_fn,
            "to_mel": self.to_mel,
            "mel_fn_args": self.mel_fn_args,
            "f0_fn": self.f0_fn,
            
            # additional models
            "vad_model": self.vad_model,
        }
        return models
    
    def get_models(self):
        """获取模型"""
        return self.models
    
    def cal_model_params(self, model:torch.nn.Module):
        """计算模型参数量"""
        total_params = sum(p.numel() for p in model.parameters())
        return total_params
    
    @timer_decorator
    def _load_dit_model(self):
        """dit model"""
        
        self.logger.info("===> Loading DiT model")
        
        dit_checkpoint_path, dit_config_path = load_custom_model_from_hf(self.cfg.dit_repo_id,
                                                                         self.cfg.dit_model_filename,
                                                                         self.cfg.dit_config_filename)
        
        # 这里尝试load fintune之后的模型看看
        # dit_checkpoint_path = "/root/autodl-tmp/seed-vc-cus/runs/csmsc_fintune_10/ft_model.pth"
        # dit_config_path = "/root/autodl-tmp/seed-vc-cus/runs/csmsc_fintune_10/config_dit_mel_seed_uvit_xlsr_tiny.yml"
        
        # dit_checkpoint_path = "/root/autodl-tmp/seed-vc-cus/runs/csmsc_fintune_10_bigvgan/ft_model.pth"
        # dit_config_path = "/root/autodl-tmp/seed-vc-cus/runs/csmsc_fintune_10_bigvgan/config_dit_mel_seed_uvit_xlsr_tiny_bigvgan.yml"
        
        self.logger.info(f"Dit_checkpoint_path: {dit_checkpoint_path}")
        self.logger.info(f"Dit_config_path: {dit_config_path}")
        
        # load
        config = yaml.safe_load(open(dit_config_path, "r"))
        model_params = recursive_munch(config["model_params"])
        model_params.dit_type = 'DiT'
        dit_model = build_model(model_params, stage="DiT")
        sr = config["preprocess_params"]["sr"]

        # Load checkpoints
        dit_model, _, _, _ = load_checkpoint(
            dit_model,
            None,
            dit_checkpoint_path,
            load_only_params=True,
            ignore_modules=[],
            is_distributed=False,
        )
        for key in dit_model:
            dit_model[key].eval()
            dit_model[key].to(self.device)
        dit_model.cfm.estimator.setup_caches(max_batch_size=1, max_seq_length=8192)  
        dit_fn = dit_model.cfm.inference
        
        # 计算dit_mdoel的参数量
        for key in dit_model:
           temp_model = dit_model[key]
           total_params = self.cal_model_params(temp_model)
           self.logger.info(f"DiT model -> {key} -> parameters: {total_params / 1_000_000:.2f}M")         
        
        return dit_model, dit_fn, config, model_params, sr
    
    @timer_decorator
    def _load_campplus_model(self):
        """加载campplus模型"""
        
        self.logger.info("===> Loading CampPlus model")

        from externals.seed_vc.modules.campplus.DTDNN import CAMPPlus

        campplus_ckpt_path = load_custom_model_from_hf(
            "funasr/campplus", "campplus_cn_common.bin", config_filename=None
        )
        campplus_model = CAMPPlus(feat_dim=80, embedding_size=192)
        campplus_model.load_state_dict(torch.load(campplus_ckpt_path, map_location="cpu"))
        campplus_model.eval()
        campplus_model.to(self.device)
        
        # 计算campplus_model的参数量
        total_params = self.cal_model_params(campplus_model)
        self.logger.info(f"CampPlus model has parameters: {total_params / 1_000_000:.2f}M")
        
        return campplus_model
    
    @timer_decorator
    def _load_vocoder_fn(self):
        """加载vocoder模型"""
        
        self.logger.info("===> Loading vocoder model")
        vocoder_type = self.model_params.vocoder.type

        if vocoder_type == 'bigvgan':  # bigvgan
            from externals.seed_vc.modules.bigvgan import bigvgan
            bigvgan_name = self.model_params.vocoder.name  #  # bigvgan_name = "nvidia/bigvgan_v2_22khz_80band_256x"
            bigvgan_model = bigvgan.BigVGAN.from_pretrained(bigvgan_name, use_cuda_kernel=False)
            # remove weight norm in the model and set to eval mode
            bigvgan_model.remove_weight_norm()
            bigvgan_model = bigvgan_model.eval().to(self.device)
            vocoder_fn = bigvgan_model
        elif vocoder_type == 'hifigan':
            from externals.seed_vc.modules.hifigan.generator import HiFTGenerator
            from externals.seed_vc.modules.hifigan.f0_predictor import ConvRNNF0Predictor
            hift_config = yaml.safe_load(open(SEED_VC_PATH / 'configs/hifigan.yml', 'r'))
            hift_gen = HiFTGenerator(**hift_config['hift'], f0_predictor=ConvRNNF0Predictor(**hift_config['f0_predictor']))
            hift_path = load_custom_model_from_hf("FunAudioLLM/CosyVoice-300M", 'hift.pt', None)
            hift_gen.load_state_dict(torch.load(hift_path, map_location='cpu'))
            hift_gen.eval()
            hift_gen.to(self.device)
            vocoder_fn = hift_gen
        elif vocoder_type == "vocos":
            vocos_config = yaml.safe_load(open(self.model_params.vocoder.vocos.config, 'r'))
            vocos_path = self.model_params.vocoder.vocos.path
            vocos_model_params = recursive_munch(vocos_config['model_params'])
            vocos = build_model(vocos_model_params, stage='mel_vocos')
            vocos_checkpoint_path = vocos_path
            vocos, _, _, _ = load_checkpoint(vocos, None, vocos_checkpoint_path,
                                            load_only_params=True, ignore_modules=[], is_distributed=False)
            _ = [vocos[key].eval().to(self.device) for key in vocos]
            _ = [vocos[key].to(self.device) for key in vocos]
            total_params = sum(sum(p.numel() for p in vocos[key].parameters() if p.requires_grad) for key in vocos.keys())
            self.logger.info(f"Vocoder model total parameters: {total_params / 1_000_000:.2f}M")
            vocoder_fn = vocos.decoder
        else:
            raise ValueError(f"Unknown vocoder type: {vocoder_type}")
        
        # 计算vocoder_fn的参数量
        total_params = self.cal_model_params(vocoder_fn)
        self.logger.info(f"vocoder_fn has parameters: {total_params / 1_000_000:.2f}M")
        
        return vocoder_fn
    
    @timer_decorator
    def _load_semantic_fn(self):
        """加载语义模型"""
        
        self.logger.info("===> Loading semantic model")
        speech_tokenizer_type = self.model_params.speech_tokenizer.type
        if speech_tokenizer_type == 'whisper':
            # whisper
            from transformers import AutoFeatureExtractor, WhisperModel
            whisper_name = self.model_params.speech_tokenizer.name
            whisper_model = WhisperModel.from_pretrained(whisper_name, torch_dtype=torch.float16).to(self.device)
            del whisper_model.decoder
            whisper_feature_extractor = AutoFeatureExtractor.from_pretrained(whisper_name)
            
            # 计算whisper_model的参数量
            total_params = self.cal_model_params(whisper_model)
            self.logger.info(f"Semantic -> Whisper model -> parameters: {total_params / 1_000_000:.2f}M")

            def semantic_fn(waves_16k):
                ori_inputs = whisper_feature_extractor([waves_16k.squeeze(0).cpu().numpy()],
                                                    return_tensors="pt",
                                                    return_attention_mask=True)  # 计算mel频谱
                ori_input_features = whisper_model._mask_input_features(
                    ori_inputs.input_features, attention_mask=ori_inputs.attention_mask
                    ).to(self.device)  # 对输入特征进行掩码处理，模拟训练时的 dropout
                with torch.no_grad():
                    ori_outputs = whisper_model.encoder(
                        ori_input_features.to(whisper_model.encoder.dtype),
                        head_mask=None,
                        output_attentions=False,
                        output_hidden_states=False,
                        return_dict=True,
                    )
                S_ori = ori_outputs.last_hidden_state.to(torch.float32)  # [batch, length, dim]
                S_ori = S_ori[:, :waves_16k.size(-1) // 320 + 1]  # whisper downsample 320x 
                                                                  # (hop_size=160, cnn_stride=2)
                return S_ori
        elif speech_tokenizer_type == 'cnhubert':
            from transformers import (
                Wav2Vec2FeatureExtractor,
                HubertModel,
            )
            hubert_model_name = self.dit_config['model_params']['speech_tokenizer']['name']
            hubert_feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(hubert_model_name)
            hubert_model = HubertModel.from_pretrained(hubert_model_name)
            hubert_model = hubert_model.to(self.device)
            hubert_model = hubert_model.eval()
            hubert_model = hubert_model.half()
            
            # 计算hubert_model的参数量
            total_params = self.cal_model_params(hubert_model)
            self.logger.info(f"Semantic -> HuBERT model -> parameters: {total_params / 1_000_000:.2f}M")

            def semantic_fn(waves_16k):
                ori_waves_16k_input_list = [
                    waves_16k[bib].cpu().numpy()
                    for bib in range(len(waves_16k))
                ]
                ori_inputs = hubert_feature_extractor(ori_waves_16k_input_list,
                                                    return_tensors="pt",
                                                    return_attention_mask=True,
                                                    padding=True,
                                                    sampling_rate=16000).to(self.device)
                with torch.no_grad():
                    ori_outputs = hubert_model(
                        ori_inputs.input_values.half(),
                    )
                S_ori = ori_outputs.last_hidden_state.float()
                return S_ori
        elif speech_tokenizer_type == 'xlsr':
            from transformers import (
                Wav2Vec2FeatureExtractor,
                Wav2Vec2Model,
            )
            model_name = self.dit_config['model_params']['speech_tokenizer']['name']
            output_layer = self.dit_config['model_params']['speech_tokenizer']['output_layer']
            wav2vec_feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
            wav2vec_model = Wav2Vec2Model.from_pretrained(model_name)
            wav2vec_model.encoder.layers = wav2vec_model.encoder.layers[:output_layer]
            wav2vec_model = wav2vec_model.to(self.device)
            wav2vec_model = wav2vec_model.eval()
            wav2vec_model = wav2vec_model.half()
            
            # 计算wav2vec_model的参数量
            total_params = self.cal_model_params(wav2vec_model)
            self.logger.info(f"Semantic -> Wav2Vec model -> parameters: {total_params / 1_000_000:.2f}M")
            

            def semantic_fn(waves_16k):
                ori_waves_16k_input_list = [
                    waves_16k[bib].cpu().numpy()
                    for bib in range(len(waves_16k))
                ]
                ori_inputs = wav2vec_feature_extractor(ori_waves_16k_input_list,
                                                    return_tensors="pt",
                                                    return_attention_mask=True,
                                                    padding=True,
                                                    sampling_rate=16000).to(self.device)
                with torch.no_grad():
                    ori_outputs = wav2vec_model(
                        ori_inputs.input_values.half(),
                    )
                S_ori = ori_outputs.last_hidden_state.float()
                return S_ori
        else:
            raise ValueError(f"Unknown speech tokenizer type: {speech_tokenizer_type}")
        
        return semantic_fn

    def _load_mel(self):
        """加载mel"""
        
        # Generate mel spectrograms
        mel_fn_args = {
            "n_fft": self.dit_config['preprocess_params']['spect_params']['n_fft'],  # tiny=1024, small=1024, base=2048
            "win_size": self.dit_config['preprocess_params']['spect_params']['win_length'],  # tiny=1024, small=1024, base=2048
            "hop_size": self.dit_config['preprocess_params']['spect_params']['hop_length'],  # tiny=256, small=256, base=512
            "num_mels": self.dit_config['preprocess_params']['spect_params']['n_mels'],  # tiny=80, small=80, base=128
            "sampling_rate": self.sr,  # tiny=22050, small=22050, base=44100
            "fmin": self.dit_config['preprocess_params']['spect_params'].get('fmin', 0),  # tiny=0, small=0, base=0
            "fmax": None if self.dit_config['preprocess_params']['spect_params'].get('fmax', "None") == "None" else 8000,  # tiny=8000, small="None", base="None"
            "center": False
        }
        from externals.seed_vc.modules.audio import mel_spectrogram
        to_mel = lambda x: mel_spectrogram(x, **mel_fn_args)
        
        return to_mel, mel_fn_args
        
    def _torch_compile(self):
        """torch.compile 加速"""
        # 这里用 torch.compile() 加速一下看看
        self.semantic_fn = torch.compile(self.semantic_fn, mode="max-autotune")  # fullgraph=True 先不用
        self.dit_fn = torch.compile(self.dit_fn, mode="max-autotune")
        # vocoder_fn = torch.compile(self.vocoder_fn, mode="max-autotune")  # mode="max-autotune"
        
    @timer_decorator
    def _load_vad_model(self):
        """加载vad模型"""
        
        self.logger.info("===> Loading VAD model")
        from funasr import AutoModel
        try: 
            vad_model = AutoModel(model="fsmn-vad", model_revision="v2.0.4")
        except:
            # try loading from local path
            vad_model_path = self.modelscope_cache_path / "hub/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
            vad_model = AutoModel(model=vad_model_path) 
        
        
        # 计算vad_model的参数量
        total_params = self.cal_model_params(vad_model.model)
        self.logger.info(f"VAD model has parameters: {total_params / 1_000_000:.2f}M")
        
        return vad_model
    
    @timer_decorator
    def _load_f0_fn(self):
        # f0 extractor
        from externals.seed_vc.modules.rmvpe import RMVPE
        model_path = load_custom_model_from_hf("lj1995/VoiceConversionWebUI", "rmvpe.pt", None)
        rmvpe = RMVPE(model_path, is_half=False, device=self.device)
        f0_fn = rmvpe.infer_from_audio
        
        return f0_fn
    
      
if __name__ == "__main__":
    print('starting model factory...')
    model_config = ModelConfig()
    model_factory = ModelFactory(model_config)
    models = model_factory.get_models()
    print('-' * 42)
    print(f"Models loaded successfully.")
    print(models.keys())
