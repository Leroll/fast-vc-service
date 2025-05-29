import asyncio
import websockets
import soundfile as sf
import numpy as np
import argparse
import time
import json
from pathlib import Path
from tqdm import tqdm
import resampy
import opuslib  # For opus encoding
from bson import ObjectId
from loguru import logger


def read_audio_file(audio_path, encoding,
                    output_wav_dir):
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
                
    # Ensure sample rate is compatible with Opus             
    if encoding == "OPUS":  
        opus_sample_rates = [8000, 12000, 16000, 24000, 48000]
        if sample_rate not in opus_sample_rates:
            closest_rate = min(opus_sample_rates, key=lambda x: abs(x - sample_rate))
            logger.warning(f"Sample rate {sample_rate} Hz not supported by Opus. Resampling to {closest_rate} Hz")
            audio = resampy.resample(audio, sample_rate, closest_rate)
            sample_rate = closest_rate
                
    # Generate output path based on input filename
    output_dir = Path(output_wav_dir)
    output_dir.mkdir(parents=True, exist_ok=True)  # Ensure output directory exists
    input_path = Path(audio_path)
    output_filename = f"{input_path.stem}_ws-client-vc{input_path.suffix}"
    output_path = output_dir / output_filename
    
    return audio, sample_rate, output_path

def cal_chunk_frame_size(sample_rate, encoding, 
                         chunk_time_ms, frame_duration_ms):
    """
    Calculate the number of audio samples per chunk based on the sample rate
    and desired chunk time in milliseconds.
    
    Args:
        sample_rate: Sample rate of the audio file
        chunk_time_ms: Desired chunk time in milliseconds
    
    Returns:
        Number of samples per chunk
    """
    if encoding == "OPUS":
        # For Opus, we use 20ms frames (standard)
        chunk_frame = int(frame_duration_ms / 1000 * sample_rate )
    elif encoding == "PCM":
        # For PCM, calculate based on chunk time
        chunk_frame = int(sample_rate / 1000 * chunk_time_ms )
    
    return chunk_frame
    

async def send_audio_file(websocket_url, api_key, 
                          real_time_simulation,
                          # wav params
                          audio_path, output_wav_dir="wavs/outputs/clients",
                          encoding="PCM",
                          # pcm params 
                          chunk_time_ms=500,
                          # opus params
                          bitrate=128_000,
                          frame_duration_ms=20,  # 帧大小
                         ):
    """
    Send an audio file to the voice conversion service in chunks,
    simulating real-time streaming.
    
    Args:
        websocket_url: URL of the websocket service
        api_key: API key for authentication
        real_time_simulation: If True, simulate real-time sending of audio chunks
        
        audio_path: Path to the input audio file
        output_wav_dir: Directory to save output audio files
        encoding: Format to send audio in ("PCM" or "OPUS")
        
        chunk_time_ms: Time in ms for each audio chunk (default: 500ms)
        
        bitrate: Bitrate for Opus encoding (default: 128k bps)
        frame_duration_ms: Duration of each Opus frame in ms (default: 20ms)
    """
    try:
        assert encoding in ["PCM", "OPUS"], "Encoding must be either 'PCM' or 'OPUS'"
        
        # Generate session ID
        session_id = str(ObjectId())
        logger.info(f"Generated session ID: {session_id}")
        
        # read audio file
        audio, sample_rate, output_path = read_audio_file(audio_path, encoding,  
                                                          output_wav_dir)
        logger.info(f"Audio loaded: {len(audio)} samples at {sample_rate} Hz")
        
        # cal chunk frame size
        chunk_frame = cal_chunk_frame_size(sample_rate, encoding,
                                           chunk_time_ms, frame_duration_ms)
        logger.info(f"Chunk frame size: {chunk_frame}")
        total_chunks = len(audio) // chunk_frame + (1 if len(audio) % chunk_frame else 0)
        logger.info(f"Audio will be split into {total_chunks} chunks of {chunk_frame} samples each")
                
        # Initialize Opus encoder if needed
        if encoding == "OPUS":
            # APPLICATION has three modes: AUDIO, VOIP, LOWDELAY
            # the rank of quality is AuDIO > VOIP > LOWDELAY
            # For voice conversion, we typically use AUDIO mode
            opus_encoder = opuslib.Encoder(sample_rate, 1, opuslib.APPLICATION_AUDIO) 
            opus_encoder.bitrate = bitrate  # Set bitrate
        
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
                    logger.info(f"Error: Unexpected response: {response_data}")
                    return
                logger.info(f"Server ready: {response_data['message']}")
            except asyncio.TimeoutError:
                logger.info("Timeout waiting for server ready signal")
                return
            
            # Create separate task for receiving messages
            receive_queue = asyncio.Queue()
            
            async def receive_messages():
                while True:
                    try:
                        response = await websocket.recv()
                        await receive_queue.put(response)
                    except websockets.exceptions.ConnectionClosed:
                        logger.info("WebSocket connection closed")
                        break
                    except Exception as e:
                        logger.info(f"Error receiving message: {e}")
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
                            logger.info(f"Received audio: {len(converted_chunk)} samples")
                        else:
                            # It's a control message
                            try:
                                response_data = json.loads(response)
                                if response_data["type"] == "complete":
                                    logger.info(f"Processing complete: {response_data}")
                                    return True
                                elif response_data["type"] == "error":
                                    logger.info(f"Error from server: {response_data}")
                                    return False
                                else:
                                    logger.info(f"Received message: {response_data}")
                            except json.JSONDecodeError:
                                logger.info(f"Received non-JSON text: {response}")
                    except asyncio.TimeoutError:
                        # Just a timeout on the queue, continue
                        continue
                    except asyncio.CancelledError:
                        # Task was cancelled, exit gracefully
                        return False
                    except Exception as e:
                        logger.info(f"Error processing response: {e}")
                        return False
            
            processor_task = asyncio.create_task(process_responses())
            
            # Send audio in chunks with progress bar
            with tqdm(total=total_chunks, desc="Sending audio chunks") as pbar:
                for i in range(0, len(audio), chunk_frame):
                    
                    # Get the current chunk
                    chunk = audio[i:i+chunk_frame]
                    if len(chunk) < chunk_frame:  # Pad the last chunk if needed
                        chunk = np.pad(chunk, (0, chunk_frame - len(chunk)))
                    
                    chunk_int16 = (chunk * 32768).astype(np.int16)
                    chunk_to_send = chunk_int16.tobytes()
                    if encoding == "OPUS":
                        chunk_to_send = opus_encoder.encode(chunk_to_send, chunk_frame)

                    # Send the chunk
                    chunk_start_time = time.perf_counter()
                    await websocket.send(chunk_to_send)
                    
                    # If simulating real-time, wait appropriate amount of time
                    if real_time_simulation:
                        elapsed = (time.perf_counter() - chunk_start_time) * 1000
                        package_time_ms = chunk_time_ms if encoding == "PCM" else frame_duration_ms
                        wait_time = max(0, package_time_ms - elapsed)
                        if wait_time > 0:
                            await asyncio.sleep(wait_time / 1000)
                            
                    pbar.update(1)
            
            # Send end signal
            logger.info("Sending end signal")
            await websocket.send(json.dumps({"type": "end"}))
            
            # Wait for processing to complete
            try:
                completion = await asyncio.wait_for(processor_task, timeout=10.0)
                if completion:
                    logger.info("Successfully completed voice conversion")
                else:
                    logger.info("Voice conversion completed with errors")
            except asyncio.TimeoutError:
                logger.info("Timeout waiting for completion")
            
            # Clean up both tasks
            receiver_task.cancel()
            processor_task.cancel()
            
            # Wait for both tasks to complete cancellation
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
            
            try:
                await processor_task
            except asyncio.CancelledError:
                pass
            
            # Save the output audio
            if output_audio:
                output_audio_array = np.concatenate(output_audio)
                sf.write(output_path, output_audio_array, 16000)  # server expects 16kHz output
                logger.info(f"Saved converted audio to {output_path} ({len(output_audio_array)} samples)")
                
                # Calculate audio length
                audio_length_seconds = len(output_audio_array) / 16000 
                logger.info(f"Output audio duration: {audio_length_seconds:.2f} seconds")
            else:
                logger.info("No output audio received")
                
    except Exception as e:
        import traceback
        logger.info(f"Error during processing: {traceback.format_exc()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket client for voice conversion")
    
    parser.add_argument("--source-wav-path", 
                        default="wavs/cases/低沉男性-YL-2025-03-14.wav", 
                        help="Path to source audio file")
    
    parser.add_argument("--output-wav-dir", 
                        default="wavs/outputs/clients", 
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
                        help="Chunk time in ms for sending audio (default: 20ms)")
    
    parser.add_argument("--real-time", 
                        action="store_true", 
                        help="Simulate real-time audio sending")
    
    parser.add_argument("--encoding",
                       choices=["PCM", "OPUS"],
                       default="PCM",
                       help="Audio encoding format (PCM or OPUS)")
    
    parser.add_argument("--bitrate",
                       type=int,
                       default=128000,
                       help="Bitrate for OPUS encoding (default: 128000)")
    
    parser.add_argument("--frame-duration",
                       type=int,
                       default=20,
                       help="Frame duration in ms for OPUS encoding (default: 20)")
    
    args = parser.parse_args()
    
    asyncio.run(send_audio_file(
        websocket_url=args.url,
        api_key=args.api_key,
        real_time_simulation=args.real_time,
        audio_path=args.source_wav_path,
        output_wav_dir=args.output_wav_dir,
        encoding=args.encoding,
        chunk_time_ms=args.chunk_time,
        bitrate=args.bitrate,
        frame_duration_ms=args.frame_duration,
    ))