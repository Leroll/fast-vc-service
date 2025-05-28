import asyncio
import websockets
import soundfile as sf
import numpy as np
import argparse
import uuid
import time
import json
from pathlib import Path
from tqdm import tqdm
import resampy
import opuslib  # For opus encoding

async def send_audio_file(websocket_url, audio_path, output_path, api_key, 
                         chunk_time_ms=500, real_time_simulation=False,
                         audio_format="pcm"):
    """
    Send an audio file to the voice conversion service in chunks,
    simulating real-time streaming.
    
    Args:
        websocket_url: URL of the websocket service
        audio_path: Path to the input audio file
        output_path: Path to save the converted audio
        api_key: API key for authentication
        chunk_time_ms: Time in ms for each audio chunk (default: 500ms)
        real_time_simulation: If True, simulate real-time sending of audio chunks
        audio_format: Format to send audio in ('pcm' or 'opus')
    """
    try:
        # Read audio file
        print(f"Reading audio file: {audio_path}")
        audio, sample_rate = sf.read(audio_path)
        if len(audio.shape) > 1:
            print(f"Converting {audio.shape[1]}-channel audio to mono")
            audio = audio[:, 0]
        
        # Ensure audio is float32 normalized between -1 and 1
        if audio.dtype != np.float32:
            if audio.dtype == np.int16:
                audio = audio.astype(np.float32) / 32768.0
            elif audio.dtype == np.int32:
                audio = audio.astype(np.float32) / 2147483648.0
            else:
                audio = audio.astype(np.float32)
                if np.max(np.abs(audio)) > 1.0:
                    audio /= np.max(np.abs(audio))
                    
        # Generate session ID
        session_id = str(uuid.uuid4())
        print(f"Generated session ID: {session_id}")
        
        # Initialize Opus encoder if needed
        opus_encoder = None
        encoding = audio_format.upper()
        if encoding == "OPUS":
            # Ensure sample rate is compatible with Opus
            opus_sample_rates = [8000, 12000, 16000, 24000, 48000]
            if sample_rate not in opus_sample_rates:
                closest_rate = min(opus_sample_rates, key=lambda x: abs(x - sample_rate))
                print(f"Warning: Sample rate {sample_rate} Hz not supported by Opus. Resampling to {closest_rate} Hz")
                audio = resampy.resample(audio, sample_rate, closest_rate)
                sample_rate = closest_rate
                
            # Create Opus encoder using high-level API
            opus_encoder = opuslib.Encoder(sample_rate, 1, opuslib.APPLICATION_AUDIO)
            
            # For Opus, we use 20ms frame size (standard)
            opus_frame_samples = int(0.02 * sample_rate)  # 20ms frames
            chunk_samples = opus_frame_samples
            print(f"Using Opus encoding with {opus_frame_samples} samples per frame ({chunk_samples/sample_rate*1000:.1f}ms)")
        else:
            # For PCM, use the specified chunk time
            chunk_samples = int(sample_rate * chunk_time_ms / 1000)
            print(f"Using PCM encoding with {chunk_samples} samples per chunk ({chunk_time_ms}ms)")
        
        total_chunks = len(audio) // chunk_samples + (1 if len(audio) % chunk_samples else 0)
        print(f"Audio will be split into {total_chunks} chunks of {chunk_samples} samples each")
        
        # Prepare output buffer for received audio
        output_audio = []
        
        async with websockets.connect(websocket_url) as websocket:
            # Send config
            config = {
                "type": "config",
                "session_id": session_id,
                "api_key": api_key,
                "audio_format": {
                    "sample_rate": sample_rate,
                    "bit_depth": 16,
                    "channels": 1,
                    "encoding": encoding
                }
            }
            await websocket.send(json.dumps(config))
            print(f"Sent configuration to server: {json.dumps(config)}")
            
            # Wait for ready signal
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                response_data = json.loads(response)
                if response_data["type"] != "ready":
                    print(f"Error: Unexpected response: {response_data}")
                    return
                print(f"Server ready: {response_data['message']}")
            except asyncio.TimeoutError:
                print("Timeout waiting for server ready signal")
                return
            
            # Create separate task for receiving messages
            receive_queue = asyncio.Queue()
            
            async def receive_messages():
                while True:
                    try:
                        response = await websocket.recv()
                        await receive_queue.put(response)
                    except websockets.exceptions.ConnectionClosed:
                        print("WebSocket connection closed")
                        break
                    except Exception as e:
                        print(f"Error receiving message: {e}")
                        break
            
            receiver_task = asyncio.create_task(receive_messages())
            
            # Process responses in background
            async def process_responses():
                while True:
                    try:
                        response = await asyncio.wait_for(receive_queue.get(), timeout=0.1)
                        
                        if isinstance(response, bytes):
                            # Convert bytes back to numpy array
                            converted_chunk = np.frombuffer(response, dtype=np.int16).astype(np.float32) / 32768.0
                            output_audio.append(converted_chunk)
                            print(f"Received audio: {len(converted_chunk)} samples")
                        else:
                            # It's a control message
                            try:
                                response_data = json.loads(response)
                                if response_data["type"] == "complete":
                                    print(f"Processing complete: {response_data}")
                                    return True
                                elif response_data["type"] == "error":
                                    print(f"Error from server: {response_data}")
                                    return False
                                else:
                                    print(f"Received message: {response_data}")
                            except json.JSONDecodeError:
                                print(f"Received non-JSON text: {response}")
                    except asyncio.TimeoutError:
                        # Just a timeout on the queue, continue
                        continue
                    except asyncio.CancelledError:
                        # Task was cancelled, exit gracefully
                        return False
                    except Exception as e:
                        print(f"Error processing response: {e}")
                        return False
            
            processor_task = asyncio.create_task(process_responses())
            
            # Send audio in chunks with progress bar
            with tqdm(total=total_chunks, desc="Sending audio chunks") as pbar:
                for i in range(0, len(audio), chunk_samples):
                    chunk = audio[i:i+chunk_samples]
                    
                    # Pad the last chunk if needed
                    if len(chunk) < chunk_samples:
                        chunk = np.pad(chunk, (0, chunk_samples - len(chunk)))
                    
                    # Process according to format
                    if encoding == "OPUS":
                        # Convert to int16 for Opus encoding
                        chunk_int16 = (chunk * 32768).astype(np.int16)
                        
                        # Encode with Opus using high-level API
                        chunk_to_send = opus_encoder.encode(chunk_int16.tobytes(), chunk_samples)
                    else:
                        # Standard PCM conversion
                        chunk_int16 = (chunk * 32768).astype(np.int16)
                        chunk_to_send = chunk_int16.tobytes()
                    
                    chunk_start_time = time.time()
                    await websocket.send(chunk_to_send)
                    
                    # If simulating real-time, wait appropriate amount of time
                    if real_time_simulation:
                        elapsed = (time.time() - chunk_start_time) * 1000
                        wait_time = max(0, chunk_time_ms - elapsed)
                        if wait_time > 0:
                            await asyncio.sleep(wait_time / 1000)
                    
                    pbar.update(1)
            
            # Send end signal
            print("Sending end signal")
            await websocket.send(json.dumps({"type": "end"}))
            
            # Wait for processing to complete
            try:
                completion = await asyncio.wait_for(processor_task, timeout=10.0)
                if completion:
                    print("Successfully completed voice conversion")
                else:
                    print("Voice conversion completed with errors")
            except asyncio.TimeoutError:
                print("Timeout waiting for completion")
            
            # Clean up
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
            
            # Save the output audio
            if output_audio:
                output_audio_array = np.concatenate(output_audio)
                sf.write(output_path, output_audio_array, sample_rate)
                print(f"Saved converted audio to {output_path} ({len(output_audio_array)} samples)")
                
                # Calculate audio length
                audio_length_seconds = len(output_audio_array) / sample_rate
                print(f"Output audio duration: {audio_length_seconds:.2f} seconds")
            else:
                print("No output audio received")
                
    except Exception as e:
        import traceback
        print(f"Error during processing: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket client for voice conversion")
    
    parser.add_argument("--source-wav-path", 
                        default="wavs/cases/低沉男性-YL-2025-03-14.wav", 
                        help="Path to source audio file")
    
    parser.add_argument("--output-wav-dir", 
                        default="wavs/outputs", 
                        help="Directory to save output audio files")
    
    parser.add_argument("--url", 
                        default="ws://localhost:8042/ws", 
                        help="WebSocket URL")
    
    parser.add_argument("--api-key", 
                        default="test-key", 
                        help="API key for authentication")
    
    parser.add_argument("--chunk-time", 
                        type=int, 
                        default=20, 
                        help="Chunk time in ms for sending audio (default: 20)")
    
    parser.add_argument("--real-time", 
                        action="store_true", 
                        help="Simulate real-time audio sending")
    
    parser.add_argument("--format",
                       choices=["pcm", "opus"],
                       default="pcm",
                       help="Audio format to send (pcm or opus)")
    
    args = parser.parse_args()
    
    # Generate output path based on input filename
    output_dir = Path(args.output_wav_dir)
    input_path = Path(args.source_wav_path)
    output_filename = f"{input_path.stem}_ws-client-vc{input_path.suffix}"
    output_path = output_dir / output_filename
    
    asyncio.run(send_audio_file(
        args.url, 
        args.source_wav_path,
        str(output_path),
        args.api_key,
        args.chunk_time,
        args.real_time,
        args.format,
    ))