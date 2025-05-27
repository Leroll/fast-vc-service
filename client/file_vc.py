"""
For testing the Performance of realtime_vc
"""
from pathlib import Path
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # add parent directory to path

from realtime_vc import RealtimeVoiceConversion, RealtimeVoiceConversionConfig

def parse_args():
    parser = argparse.ArgumentParser(description="批量语音转换脚本")
    
    parser.add_argument('--wav_files', type=str, 
                        default=None, 
                        help="要处理的文件列表 (空格分隔的字符串), 没传默认为 None")
    
    parser.add_argument('--reference_audio_path', type=str, 
                        default="wavs/references/csmsc042-s0.2.wav",
                        # default="wavs/references/csmsc042.wav", 
                        # default="wavs/references/csmsc042-s0.5.wav",
                        # default="wavs/references/csmsc042-s1.0.wav",
                        help="参考音频文件路径")
    
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
                        default=0,
                        help="输入输出 rmx_mix 比例，0.0 代表只使用输入音频，1.0 代表只使用输出音频")
    
    parser.add_argument("--zc_framerate", type=int,
                        default=50,
                        help="精度因子zc的帧率控制，zc_duration =  1s//zc_framerate,  rvc=100, seed-vc=50")

    return parser.parse_args()


if __name__ == "__main__":
    # 1. parse args
    args = parse_args()

    wav_files = args.wav_files.split() if args.wav_files else None  
    if wav_files is None:  
        # wav files
        wav_files = ["wavs/cases/低沉男性-YL-2025-03-14.wav"]  
        
        # wav directory
        # src_path = Path("wavs/cases")
        # wav_files = [file for file in src_path.iterdir() if file.is_file() and file.name.split('.')[-1] in ['wav']]

    # 2. create stream vc decoder
    Path(args.save_dir).mkdir(parents=True, exist_ok=True)
    cfg = RealtimeVoiceConversionConfig(block_time=args.block_time,
                                crossfade_time=args.crossfade_time,
                                diffusion_steps=args.diffusion_steps, 
                                reference_audio_path=args.reference_audio_path, 
                                save_dir=args.save_dir,
                                max_prompt_length=args.max_prompt_length,
                                rms_mix_rate=args.rms_mix_rate,
                                zc_framerate=args.zc_framerate,
                                arbitrary_types_allowed=True,  # 这里允许任意类型
                                )
    print(cfg)
    realtime_vc = RealtimeVoiceConversion(cfg=cfg)

    # 3. begin to process
    print('-' * 42)
    print("press Enter to start voice conversion...")
    try:
        input()
    except EOFError:
        pass  # 忽略 EOFError，直接继续

    for file in wav_files:
        realtime_vc.file_vc(file)
                
    realtime_vc._performance_report()