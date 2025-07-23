#!/usr/bin/env python3
"""
F0 analysis tool using RMVPE
Extracts F0 and provides comprehensive analysis including statistics, visualization, and musical note conversion.
"""

import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import librosa
import torch
import fire

# Add project paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent # Go up 3 levels: tools -> fast_vc_service -> src -> project_root
SEED_VC_PATH = PROJECT_ROOT / "externals" / "seed_vc"

# Add project root path to sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Add seed-vc path to sys.path
if str(SEED_VC_PATH) not in sys.path:
    sys.path.append(str(SEED_VC_PATH))

from externals.seed_vc.modules.rmvpe import RMVPE
from externals.seed_vc.hf_utils import load_custom_model_from_hf


def load_rmvpe_model(device="cuda" if torch.cuda.is_available() else "cpu"):
    """Load RMVPE model"""
    print("Loading RMVPE model...")
    model_path = load_custom_model_from_hf("lj1995/VoiceConversionWebUI", "rmvpe.pt", None)
    rmvpe = RMVPE(model_path, is_half=False, device=device)
    print(f"RMVPE model loaded on {device}")
    return rmvpe


def load_audio(audio_path, target_sr=16000):
    """Load audio file and resample to target sampling rate"""
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    print(f"Loading audio: {audio_path}")
    audio, sr = librosa.load(audio_path, sr=None)
    
    if sr != target_sr:
        print(f"Resampling from {sr}Hz to {target_sr}Hz")
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
    
    return audio, target_sr


def extract_f0(audio, sr, rmvpe, hop_length=512):
    """Extract F0 using RMVPE"""
    print("Extracting F0...")
    
    # RMVPE expects audio as numpy array
    if isinstance(audio, torch.Tensor):
        audio = audio.cpu().numpy()
    
    # Extract F0
    f0 = rmvpe.infer_from_audio(audio, thred=0.03)
    
    # Calculate time axis
    time_axis = np.arange(len(f0)) * hop_length / sr
    
    return f0, time_axis


def hz_to_note(freq):
    """Convert frequency to musical note"""
    if freq <= 0:
        return "N/A"
    
    # A4 = 440 Hz
    A4 = 440
    C0 = A4 * np.power(2, -4.75)
    
    if freq > C0:
        h = 12 * np.log2(freq / C0)
        octave = int(h // 12)
        n = int(h % 12)
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        return f"{notes[n]}{octave}"
    return "N/A"


def plot_f0(f0, time_axis, output_path=None):
    """Plot F0 contour"""
    plt.figure(figsize=(12, 6))
    
    # Plot F0
    voiced_mask = f0 > 0
    plt.plot(time_axis[voiced_mask], f0[voiced_mask], 'b-', linewidth=1.5, label='F0')
    plt.scatter(time_axis[~voiced_mask], np.zeros(np.sum(~voiced_mask)), 
                c='red', s=1, alpha=0.5, label='Unvoiced')
    
    plt.xlabel('Time (s)')
    plt.ylabel('Frequency (Hz)')
    plt.title('F0 Contour')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"F0 plot saved to: {output_path}")
    else:
        plt.show()
    
    plt.close()


def save_f0_data(f0, time_axis, output_path):
    """Save F0 data to CSV file"""
    data = np.column_stack([time_axis, f0])
    np.savetxt(output_path, data, delimiter=',', header="Time(s),F0(Hz)", fmt="%.6f", comments='')
    print(f"F0 data saved to: {output_path}")


def save_f0_stats(stats, output_path):
    """Save F0 statistics to JSON file"""
    import json
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"F0 statistics saved to: {output_path}")


def analyze_f0(f0, time_axis, f0_threshold=30):
    """Analyze F0 statistics"""
    # Remove unvoiced frames and very low frequency noise
    # Use threshold to filter minimum reasonable F0 for human voice
    voiced_f0 = f0[f0 > f0_threshold]
    
    if len(voiced_f0) == 0:
        print(f"No valid voiced frames detected (threshold: {f0_threshold}Hz)!")
        return None
    
    # Calculate statistics
    stats = {
        'total_frames': len(f0),
        'voiced_frames': len(voiced_f0),
        'unvoiced_frames': len(f0) - len(voiced_f0),
        'voiced_percentage': round(len(voiced_f0)/len(f0)*100, 2),
        'unvoiced_percentage': round((len(f0) - len(voiced_f0))/len(f0)*100, 2),
        'audio_duration': round(time_axis[-1], 2),
        'f0_mean': round(np.mean(voiced_f0), 2),
        'f0_median': round(np.median(voiced_f0), 2),
        'f0_min': round(np.min(voiced_f0), 2),
        'f0_max': round(np.max(voiced_f0), 2),
        'f0_std': round(np.std(voiced_f0), 2),
        'f0_threshold': f0_threshold,
        'f0_mean_note': hz_to_note(np.mean(voiced_f0)),
        'f0_min_note': hz_to_note(np.min(voiced_f0)),
        'f0_max_note': hz_to_note(np.max(voiced_f0))
    }
    
    print("\n" + "="*50)
    print("F0 Analysis Results:")
    print("="*50)
    print(f"F0 threshold: {f0_threshold}Hz")
    print(f"Total frames: {stats['total_frames']}")
    print(f"Voiced frames: {stats['voiced_frames']} ({stats['voiced_percentage']:.1f}%)")
    print(f"Unvoiced frames: {stats['unvoiced_frames']} ({stats['unvoiced_percentage']:.1f}%)")
    print(f"Audio duration: {stats['audio_duration']:.2f} seconds")
    print()
    print("F0 Statistics (Hz):")
    print(f"  Mean: {stats['f0_mean']:.2f}")
    print(f"  Median: {stats['f0_median']:.2f}")
    print(f"  Min: {stats['f0_min']:.2f}")
    print(f"  Max: {stats['f0_max']:.2f}")
    print(f"  Std: {stats['f0_std']:.2f}")
    print()
    print("F0 in Musical Notes (approximation):")
    print(f"  Mean: {stats['f0_mean_note']}")
    print(f"  Min: {stats['f0_min_note']}")
    print(f"  Max: {stats['f0_max_note']}")
    
    return stats


def main(
    audio_path: str,
    device: str = "auto",
    hop_length: int = 512,
    f0_threshold: float = 30.0,
    save_f0_data: bool = False
):
    """Analyze F0 using RMVPE
    
    Args:
        audio_path: Path to input audio file
        device: Device to use (cuda/cpu/auto)
        hop_length: Hop length for F0 extraction
        f0_threshold: F0 threshold for voiced frame detection (Hz)
        save_f0_data: Save F0 data to CSV file
    """
    # Determine device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    try:
        # Load RMVPE model
        rmvpe = load_rmvpe_model(device)
        
        # Load audio
        audio, sr = load_audio(audio_path)
        
        # Extract F0
        f0, time_axis = extract_f0(audio, sr, rmvpe, hop_length)
        
        # Analyze F0
        stats = analyze_f0(f0, time_axis, f0_threshold)
        
        # Generate default file paths
        audio_path_obj = Path(audio_path)
        audio_stem = audio_path_obj.stem  # filename without extension
        audio_dir = audio_path_obj.parent
        
        # Default paths
        plot_path = audio_dir / f"{audio_stem}_f0_plot.png"
        stats_path = audio_dir / f"{audio_stem}_f0_stats.json"
        
        # Always save plot and stats
        plot_f0(f0, time_axis, plot_path)
        
        if stats is not None:
            save_f0_stats(stats, stats_path)
        
        # Save F0 data only if explicitly requested
        if save_f0_data:
            csv_path = audio_dir / f"{audio_stem}_f0_data.csv"
            save_f0_data(f0, time_axis, csv_path)
        
        print("\nF0 analysis completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    """
    Usage Examples:
        # Change to the project root directory
        cd fast-vc-service 
        
        # Basic F0 analysis (default behavior)
        # Saves plot as: audio_f0_plot.png and stats as: audio_f0_stats.json
        python analyze_f0.py audio.wav
        
        # Custom F0 threshold for voice detection
        python analyze_f0.py audio.wav --f0-threshold 50
        
        # Save F0 data to CSV file
        python analyze_f0.py audio.wav --save-f0-data
        
        # Use CPU device with custom threshold
        python analyze_f0.py audio.wav --device cpu --f0-threshold 40
        
        # Custom hop length
        python analyze_f0.py audio.wav --hop-length 256
        
        # Combine options: save F0 data with custom parameters
        python analyze_f0.py audio.wav --save-f0-data --f0-threshold 35 --hop-length 256
    """
    fire.Fire(main)

