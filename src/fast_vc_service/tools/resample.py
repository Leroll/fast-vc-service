import librosa
import soundfile as sf
from pathlib import Path
import fire

def resample_audio(input_path, target_sr=16000):
    """
    Resample an audio file to a target sample rate.

    Parameters:
    - input_path: str, path to the input audio file.
    - target_sr: int, target sample rate (default is 16000 Hz).
    """
    input_path = Path(input_path)
    
    # Load the audio file with librosa
    audio, sr = librosa.load(input_path, sr=None)
    
    # Resample the audio to the target sample rate
    if sr != target_sr:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
    
    # Save the resampled audio file
    target_sr_khz = target_sr // 1000
    output_path = input_path.with_suffix(f".{target_sr_khz}khz.wav")
    sf.write(output_path, audio, target_sr)
    print(f"Resampled audio saved to: {output_path}")


if __name__ == "__main__":
    """
    usage: 
        cd fast-vc-service
        python -m fast_vc_service.tools.resample test.wav -t 16000
    """
    fire.Fire(resample_audio)