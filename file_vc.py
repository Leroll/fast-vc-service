"""
For testing the Performance of realtime_vc
"""
from pathlib import Path
import argparse
from realtime_vc import RealtimeVoiceConversion, RealtimeVoiceConversionConfig

# -------------------------
# 1. 参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="批量语音转换脚本")
    parser.add_argument('--reference_audio_path', type=str, 
                        default="wavs/references/csmsc042-s0.2.wav",
                        # default="wavs/references/csmsc042.wav", 
                        # default="wavs/references/csmsc042-s0.5.wav",
                        # default="wavs/references/csmsc042-s1.0.wav",
                        help="参考音频文件路径")
    
    parser.add_argument('--file_list', type=str, 
                        default=None, 
                        help="要处理的文件列表 (空格分隔的字符串), 没传默认为 None")
    
    parser.add_argument('--save_dir', type=str, 
                        default='wavs/outputs', 
                        help="保存目录路径")
    
    parser.add_argument('--block_time', type=float, 
                        default=0.5, 
                        help="块大小，单位秒，默认值为 0.5 秒")
    
    parser.add_argument('--crossfade_time', type=float, 
                        default=0.04, 
                        help="交叉渐变长度，单位秒，默认值为 0.04 秒")
    
    parser.add_argument('--diffusion_steps', type=int, 
                        default=10, 
                        help="扩散步骤，默认值为 3")
    
    parser.add_argument('--max_prompt_length', type=float, 
                        default=3, 
                        help="参考截断长度，单位秒，默认值为 3 秒")
    
    parser.add_argument('--rms_mix_rate', type=float,
                        default=1.0,
                        help="输入输出 rmx_mix 比例，0.0 代表只使用输入音频，1.0 代表只使用输出音频")

    return parser.parse_args()

args = parse_args()
reference_audio_path = args.reference_audio_path
file_list = args.file_list.split() if args.file_list else None
save_dir = args.save_dir 
block_time = args.block_time
crossfade_time = args.crossfade_time
diffusion_steps = args.diffusion_steps
max_prompt_length = args.max_prompt_length

if file_list is None:
    # 单通内部赋值
    file_list = ["wavs/cases/低沉男性-YL-2025-03-14.wav"]  
    
    # 文件夹内部赋值
    # src_path = Path("wavs/cases")
    # file_list = [file for file in src_path.iterdir() if file.is_file() and file.name.split('.')[-1] in ['wav']]

# 输出解析后的值
print('-'*21+"ARGS"+'-'*21)
print(f"reference_audio_path: {reference_audio_path}")
print(f"file_list: {file_list}")
print(f"save_dir: {save_dir}")
print(f"block_time: {block_time}")
print(f"crossfade_time: {crossfade_time}")
print(f"diffusion_steps: {diffusion_steps}")
print(f"max_prompt_length: {max_prompt_length}")
print('-'*42)
# --------------------------

# 2. 对应参数赋值给cfg
Path(save_dir).mkdir(parents=True, exist_ok=True)
cfg = RealtimeVoiceConversionConfig(block_time=block_time,
                            crossfade_time=crossfade_time,
                            diffusion_steps=diffusion_steps, 
                            reference_audio_path=reference_audio_path, 
                            save_dir=save_dir,
                            max_prompt_length=max_prompt_length,
                            arbitrary_types_allowed=True,  # 这里允许任意类型
                            )
print(cfg)

# 获取推理实例
realtime_vc = RealtimeVoiceConversion(cfg=cfg)

# 3. 开始VC
print('-' * 42)
print("准备工作完毕，开始文件夹批量换声, 请按回车继续...")
try:
    input()
except EOFError:
    pass  # 忽略 EOFError，直接继续

for file in file_list:
    realtime_vc.file_vc(file)
            
realtime_vc._performance_report()