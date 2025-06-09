"""
For testing the Performance of realtime_vc
"""
from pathlib import Path
import argparse
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))  # add project root to path

from fast_vc_service.realtime_vc import RealtimeVoiceConversion
from fast_vc_service.config import Config

def parse_args():
    parser = argparse.ArgumentParser(description="批量语音转换脚本")
    
    parser.add_argument('--source-wav-path', type=str, 
                        default=None, 
                        help="要处理的文件列表 (空格分隔的字符串), 没传默认为 None")
    
    return parser.parse_args()


if __name__ == "__main__":
    # 1. parse args
    args = parse_args()
    cfg = Config().get_config()
    source_wav_path = args.source_wav_path.split() if args.source_wav_path else None  
    if source_wav_path is None:  
        # wav files
        source_wav_path = ["wavs/sources/low-pitched-male-24k.wav"]  
        
        # wav directory
        # src_path = Path("wavs/sources/")
        # source_wav_path = [file for file in src_path.iterdir() if file.is_file() and file.name.split('.')[-1] in ['wav']]

    # 2. create stream vc decoder
    realtime_vc = RealtimeVoiceConversion(cfg=cfg.realtime_vc,
                                          model_cfg=cfg.models)

    # 3. begin to process
    print('-' * 42)
    print("press Enter to start voice conversion...")
    try:
        input()
    except EOFError:
        pass  # 忽略 EOFError，直接继续

    for file in source_wav_path:
        realtime_vc.file_vc(file)
                
    realtime_vc._performance_report()