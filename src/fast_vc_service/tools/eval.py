import os
from pathlib import Path
import librosa
import torch
import numpy as np  # 添加这个导入
from resemblyzer import preprocess_wav, VoiceEncoder
from typing import List, Tuple  # 添加 Tuple 导入

from externals.dnsmos.dnsmos_computor import DNSMOSComputer

device = "cuda" if torch.cuda.is_available() else "cpu"

# 初始化模型
secs_encoder = VoiceEncoder().to(device)
mos_computer = DNSMOSComputer(
    "externals/dnsmos/sig_bak_ovr.onnx",
    "externals/dnsmos/model_v8.onnx",
    device=device,
    device_id=0,
)

def calc_secs(ref_path, vc_path):
    ref_wav = preprocess_wav(ref_path)
    vc_wav = preprocess_wav(vc_path)
    ref_embed = secs_encoder.embed_utterance(ref_wav)
    vc_embed = secs_encoder.embed_utterance(vc_wav)
    secs = float(np.inner(ref_embed, vc_embed))
    return secs

def calc_mos(audio_path):
    audio, sr = librosa.load(audio_path, sr=16000)
    result = mos_computer.compute(audio, sr, False)
    return result["SIG"], result["BAK"], result["OVRL"]

def main(ref_vc_pairs: List[Tuple[str, str]], output_path: str):  # 修改类型注解
    
    secs_list, sig_list, bak_list, ovr_list = [], [], [], []
    for ref_path, vc_path in ref_vc_pairs:
        secs = calc_secs(ref_path, vc_path)
        sig, bak, ovr = calc_mos(vc_path)
        secs_list.append(secs)
        sig_list.append(sig)
        bak_list.append(bak)
        ovr_list.append(ovr)
        print(f"{Path(vc_path).stem}: SECS={secs:.4f}, SIG={sig:.4f}, BAK={bak:.4f}, OVRL={ovr:.4f}")

    # 输出平均值
    print(f"平均 SECS: {sum(secs_list)/len(secs_list):.4f}")
    print(f"平均 SIG: {sum(sig_list)/len(sig_list):.4f}")
    print(f"平均 BAK: {sum(bak_list)/len(bak_list):.4f}")
    print(f"平均 OVRL: {sum(ovr_list)/len(ovr_list):.4f}")

    # 保存结果为markdown格式
    with open(output_path, "w", encoding='utf-8') as f:
        # 写入标题
        f.write("# 语音转换评估结果\n\n")
        
        # 写入详细结果表格
        f.write("## 详细结果\n\n")
        f.write("| 参考音频 | 转换音频 | SECS | SIG | BAK | OVRL |\n")
        f.write("|---------|---------|------|-----|-----|------|\n")
        
        for i in range(len(ref_vc_pairs)):
            ref_stem = Path(ref_vc_pairs[i][0]).stem
            vc_stem = Path(ref_vc_pairs[i][1]).stem
            f.write(f"| {ref_stem} | {vc_stem} | {secs_list[i]:.4f} | {sig_list[i]:.4f} | {bak_list[i]:.4f} | {ovr_list[i]:.4f} |\n")
        
        # 写入平均值表格
        f.write("\n## 平均值统计\n\n")
        f.write("| 指标 | 数值 |\n")
        f.write("|-----|------|\n")
        f.write(f"| SECS | {sum(secs_list)/len(secs_list):.4f} |\n")
        f.write(f"| SIG | {sum(sig_list)/len(sig_list):.4f} |\n")
        f.write(f"| BAK | {sum(bak_list)/len(bak_list):.4f} |\n")
        f.write(f"| OVRL | {sum(ovr_list)/len(ovr_list):.4f} |\n")
        
        # 写入指标说明
        f.write("\n## 指标说明\n\n")
        f.write("- **SECS**: 语音相似度评分，范围0-1，越高越好\n")
        f.write("- **SIG**: 语音信号质量评分，范围1-5，越高越好\n")
        f.write("- **BAK**: 背景噪声质量评分，范围1-5，越高越好\n")
        f.write("- **OVRL**: 整体语音质量评分，范围1-5，越高越好\n")

if __name__ == "__main__":
    """
    usage:
        cd fast-vc-service
        python -m fast_vc_service.tools.eval
        
    outputs will be saved to output_dir/ref-{ref_name}__model-{model_name}.md
    """
    # Configs
    vc_dir = Path("/path/to/vc_wavs/")  #  vc wavs to be evaluated
    ref_path = Path("/path/to/ref.wav")  # reference wav  
    ref_name = "ref-name"  
    model_name = "model-name"
    output_dir = Path("/path/to/output/")
    
    
    # make list of [ref_path, vc_path]
    vc_paths = []
    for file in vc_dir.iterdir():
        if file.suffix == ".wav":
            vc_paths.append(file)
    ref_vc_pairs = [[str(ref_path.resolve()), str(vc_path.resolve())] for vc_path in vc_paths]  
    
    # make output dir and path    
    output_dir.mkdir(exist_ok=True)  
    output_path = output_dir / f"ref-{ref_name}__model-{model_name}.md"  
    
    main(ref_vc_pairs, str(output_path))