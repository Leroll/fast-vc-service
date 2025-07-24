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
import glob

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


def extract_f0(audio, sr, rmvpe):
    """Extract F0 using RMVPE"""
    print("Extracting F0...")
    
    # RMVPE expects audio as numpy array
    if isinstance(audio, torch.Tensor):
        audio = audio.cpu().numpy()
    
    # Get hop_length from RMVPE model
    # RMVPE uses hop_length=160 in its mel_extractor
    hop_length = rmvpe.mel_extractor.hop_length
    print(f"Using RMVPE model's hop_length: {hop_length}")
    
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


def process_folder(
    folder_path: str,
    device: str = "auto",
    f0_threshold: float = 30.0,
    save_f0_data: bool = False,
    recursive: bool = False
):
    """Batch process all WAV files in a folder
    
    Args:
        folder_path: Path to folder containing WAV files
        device: Device to use (cuda/cpu/auto)
        f0_threshold: F0 threshold for voiced frame detection (Hz)
        save_f0_data: Save F0 data to CSV file
        recursive: Search WAV files recursively in subfolders
    """
    # Determine device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    folder_path = Path(folder_path)
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")
    
    # Find all WAV files
    if recursive:
        wav_files = list(folder_path.rglob("*.wav")) + list(folder_path.rglob("*.WAV"))
    else:
        wav_files = list(folder_path.glob("*.wav")) + list(folder_path.glob("*.WAV"))
    
    if not wav_files:
        print(f"No WAV files found in {folder_path}")
        return
    
    print(f"Found {len(wav_files)} WAV files")
    print("="*60)
    
    try:
        # Load RMVPE model once for all files
        rmvpe = load_rmvpe_model(device)
        
        # Process each WAV file
        successful_count = 0
        failed_files = []
        
        for i, audio_path in enumerate(wav_files, 1):
            print(f"\nProcessing [{i}/{len(wav_files)}]: {audio_path.name}")
            print("-" * 50)
            
            try:
                # Load audio
                audio, sr = load_audio(str(audio_path))
                
                # Extract F0
                f0, time_axis = extract_f0(audio, sr, rmvpe)
                
                # Analyze F0
                stats = analyze_f0(f0, time_axis, f0_threshold)
                
                # Generate file paths
                audio_stem = audio_path.stem
                audio_dir = audio_path.parent
                
                # Save outputs
                plot_path = audio_dir / f"{audio_stem}_f0_plot.png"
                stats_path = audio_dir / f"{audio_stem}_f0_stats.json"
                
                # Save plot and stats
                plot_f0(f0, time_axis, plot_path)
                
                if stats is not None:
                    save_f0_stats(stats, stats_path)
                
                # Save F0 data if requested
                if save_f0_data:
                    csv_path = audio_dir / f"{audio_stem}_f0_data.csv"
                    save_f0_data(f0, time_axis, csv_path)
                
                successful_count += 1
                print(f"✓ Successfully processed: {audio_path.name}")
                
            except Exception as e:
                print(f"✗ Failed to process {audio_path.name}: {e}")
                failed_files.append(str(audio_path))
        
        # Summary
        print("\n" + "="*60)
        print("BATCH PROCESSING SUMMARY")
        print("="*60)
        print(f"Total files: {len(wav_files)}")
        print(f"Successfully processed: {successful_count}")
        print(f"Failed: {len(failed_files)}")
        
        if failed_files:
            print("\nFailed files:")
            for file in failed_files:
                print(f"  - {file}")
        
        print(f"\nBatch processing completed!")
        
    except Exception as e:
        print(f"Error during batch processing: {e}")
        sys.exit(1)


def main(
    input_path: str,
    device: str = "auto",
    f0_threshold: float = 30.0,
    save_f0_data: bool = False,
    batch_mode: bool = False,
    recursive: bool = False
):
    """Analyze F0 using RMVPE
    
    Args:
        input_path: Path to input audio file or folder (for batch processing)
        device: Device to use (cuda/cpu/auto)
        f0_threshold: F0 threshold for voiced frame detection (Hz)
        save_f0_data: Save F0 data to CSV file
        batch_mode: Enable batch processing mode for folders
        recursive: Search WAV files recursively in subfolders (only for batch mode)
    """
    input_path_obj = Path(input_path)
    
    # Auto-detect if input is a folder
    if input_path_obj.is_dir():
        if not batch_mode:
            print("Input is a folder. Enabling batch mode automatically.")
        process_folder(
            input_path,
            device=device,
            f0_threshold=f0_threshold,
            save_f0_data=save_f0_data,
            recursive=recursive
        )
    elif batch_mode:
        raise ValueError("Batch mode enabled but input is not a folder")
    else:
        # Single file processing (existing functionality)
        # Determine device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        try:
            # Load RMVPE model
            rmvpe = load_rmvpe_model(device)
            
            # Load audio
            audio, sr = load_audio(input_path)
            
            # Extract F0
            f0, time_axis = extract_f0(audio, sr, rmvpe)
            
            # Analyze F0
            stats = analyze_f0(f0, time_axis, f0_threshold)
            
            # Generate default file paths
            audio_path_obj = Path(input_path)
            audio_stem = audio_path_obj.stem
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
        
        # Single file processing (existing functionality)
        python src/fast_vc_service/tools/analyze_f0.py audio.wav
        
        # Batch process all WAV files in a folder
        python src/fast_vc_service/tools/analyze_f0.py /path/to/folder
        
        # Batch process with custom parameters
        python src/fast_vc_service/tools/analyze_f0.py /path/to/folder --f0-threshold 50 --save-f0-data
        
        # Recursive batch processing (include subfolders)
        python src/fast_vc_service/tools/analyze_f0.py /path/to/folder --recursive
        
        # Explicit batch mode (optional, auto-detected for folders)
        python src/fast_vc_service/tools/analyze_f0.py /path/to/folder --batch-mode
        
        # Single file with custom parameters
        python src/fast_vc_service/tools/analyze_f0.py audio.wav --f0-threshold 35 --save-f0-data
    """
    fire.Fire(main)

