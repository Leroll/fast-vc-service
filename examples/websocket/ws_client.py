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
import uuid
from loguru import logger
from datetime import datetime


def read_audio_file(audio_path, encoding, target_sample_rate):
    """
    Read an audio file.
    
    return audio is float32 numpy array normalized between -1 and 1,
    if encoding is OPUS, 
        it will be resampled to a compatible sample rate.
        closest in [8000, 12000, 16000, 24000, 48000]
    """
    
    # Read audio file
    logger.info(f"Reading audio file: {audio_path}")
    audio, sample_rate = sf.read(audio_path)
    if len(audio.shape) > 1:
        logger.info(f"Converting {audio.shape[1]}-channel audio to mono")
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
    
    # Resample to target sample rate if specified
    if target_sample_rate != sample_rate:
        logger.info(f"Resampling from {sample_rate} Hz to {target_sample_rate} Hz")
        audio = resampy.resample(audio, sample_rate, target_sample_rate)
        sample_rate = target_sample_rate
    
    return audio, sample_rate

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
        chunk_frame = int(chunk_time_ms / 1000 * sample_rate)
    
    return chunk_frame
    

async def send_audio_file(websocket_url, 
                          api_key,
                          # wav params
                          audio_path, 
                          real_time_simulation,
                          session_id=None,  # 允许外部传入session_id
                          save_output=True,  # 控制是否保存输出文件
                          output_wav_dir="wavs/outputs/ws_client", 
                          # encoding params
                          encoding="PCM",
                          target_sample_rate=16000,  # 添加目标采样率参数
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
        
        audio_path: Path to the input audio file
        real_time_simulation: If True, simulate real-time sending of audio chunks
        session_id: Optional session ID for tracking the conversion session
        save_output: If True, save the output audio file after conversion
        output_wav_dir: Directory to save output audio files
        
        encoding: Format to send audio in ("PCM" or "OPUS")
        target_sample_rate: Target sample rate for audio processing (default: 16000)
        chunk_time_ms: Time in ms for each audio chunk (default: 500ms)
        bitrate: Bitrate for Opus encoding (default: 128k bps)
        frame_duration_ms: Duration of each Opus frame in ms (default: 20ms)
        
    Returns:
        dict: {
            'success': bool,
            'session_id': str,
            'send_timeline': list,  # [{'timestamp': str, 'cumulative_ms': float}, ...]
            'recv_timeline': list,  # [{'timestamp': str, 'cumulative_ms': float}, ...]
            'output_path': str or None,
            'error': str or None
        }
    """
    result = {
        'success': False,
        'session_id': None,
        'send_timeline': [],
        'recv_timeline': [],
        'output_path': None,
        'error': None
    }
    
    try:
        assert encoding in ["PCM", "OPUS"], "Encoding must be either 'PCM' or 'OPUS'"
        
        # 验证采样率是否支持 Opus
        opus_sample_rates = [8000, 12000, 16000, 24000, 48000]
        if target_sample_rate not in opus_sample_rates:
            raise ValueError(f"Sample rate {target_sample_rate} Hz not supported. Must be one of: {opus_sample_rates}")
        
        # 1. before connecting, load audio file and prepare parameters
        # Generate session ID if not provided
        if session_id is None:
            # 生成带时间戳前缀的session ID
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            unique_suffix = uuid.uuid4().hex[:4]  # 取UUID的前4位保证唯一性
            session_id = f"F{timestamp}{unique_suffix}"
            logger.info(f"Generated session ID: {session_id}")
        result['session_id'] = session_id
        
        # Generate output path based on input filename
        if save_output:
            output_dir = Path(output_wav_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_filename = f"{session_id}_ws-client-output.wav"
            output_path = output_dir / output_filename
            result['output_path'] = str(output_path)
            logger.info(f"Output will be saved to: {output_path}")
        
        # read audio file with target sample rate
        audio, sample_rate = read_audio_file(audio_path, encoding, target_sample_rate)
        logger.info(f"Audio loaded: {len(audio)} samples at {sample_rate} Hz")
        
        # cal frame size of each chunk
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
        
        # Initialize timeline tracking variables
        sent_audio_ms = 0.0
        recv_audio_ms = 0.0
        
        # 2. connect to websocket server and send audio in chunks
        # Prepare output buffer for received audio
        output_audio = []
        async with websockets.connect(websocket_url) as websocket:
            # 2.1. Send config
            config = {
                "type": "config",
                "session_id": session_id,
                "api_key": api_key,
                "sample_rate": sample_rate,
                "bit_depth": 16,
                "channels": 1,
                "encoding": encoding
            }
            
            # 如果是OPUS编码，添加帧长参数
            if encoding.upper() == "OPUS":
                config["opus_frame_duration"] = frame_duration_ms
            
            await websocket.send(json.dumps(config))
            logger.info(f"Sent configuration to server: {json.dumps(config)}")
            
            # 2.2. Wait for ready signal
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
            
            # 2.3 receive and process task
            async def receive_and_process_messages():
                nonlocal recv_audio_ms
                try:
                    while True:
                        try:
                            response = await websocket.recv()
                            
                            if isinstance(response, bytes):
                                # Convert bytes back to numpy array
                                converted_chunk = np.frombuffer(response, dtype=np.int16).astype(np.float32) / 32768.0
                                output_audio.append(converted_chunk)
                                
                                # Calculate received audio duration and record timestamp
                                # received audio sample rate is always 16kHz
                                chunk_duration_ms = len(converted_chunk) / 16_000 * 1000
                                recv_audio_ms += chunk_duration_ms
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                result['recv_timeline'].append({
                                    'timestamp': timestamp,
                                    'cumulative_ms': recv_audio_ms
                                })
                                
                                logger.info(f"{session_id} | recv | {recv_audio_ms:.1f}ms")
                                
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
                        except websockets.exceptions.ConnectionClosed:
                            logger.info("WebSocket connection closed")
                            return True  # Normal completion
                        except asyncio.CancelledError:
                            logger.info("Receive task was cancelled")
                            return False
                except Exception as e:
                    logger.error(f"Error in receive and process: {e}")
                    return False
                
            receiver_processor_task = asyncio.create_task(receive_and_process_messages())
            
            # 2.4 Send task
            async def send_audio_chunks():
                nonlocal sent_audio_ms
                try:
                    for i in range(0, len(audio), chunk_frame):
                        # Get the current chunk
                        chunk = audio[i:i+chunk_frame]
                        if len(chunk) < chunk_frame:  # Pad the last chunk if needed
                            chunk = np.pad(chunk, (0, chunk_frame - len(chunk)))
                        
                        chunk_to_send = (chunk * 32768).astype(np.int16).tobytes()
                        if encoding == "OPUS":
                            chunk_to_send = opus_encoder.encode(chunk_to_send, chunk_frame)

                        # Send the chunk
                        chunk_start_time = time.perf_counter()
                        await websocket.send(chunk_to_send)
                        
                        # Calculate sent audio duration and record timestamp
                        chunk_duration_ms = len(chunk) / sample_rate * 1000
                        sent_audio_ms += chunk_duration_ms
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        result['send_timeline'].append({
                            'timestamp': timestamp,
                            'cumulative_ms': sent_audio_ms
                        })
                        
                        logger.info(f"{session_id} | send | {sent_audio_ms:.1f}ms")
                        
                        # If simulating real-time, wait appropriate amount of time
                        if real_time_simulation:
                            elapsed = (time.perf_counter() - chunk_start_time) * 1000
                            package_time_ms = chunk_time_ms if encoding == "PCM" else frame_duration_ms
                            wait_time = max(0, package_time_ms - elapsed)
                            if wait_time > 0:
                                await asyncio.sleep(wait_time / 1000)
                    
                    # Send end signal
                    logger.info("Sending end signal")
                    await websocket.send(json.dumps({"type": "end"}))
                    return True
                except Exception as e:
                    logger.error(f"Error sending audio chunks: {e}")
                    return False
                
            sender_task = asyncio.create_task(send_audio_chunks())
            
            # 2.5 Wait for all tasks to complete
            try:
                # Wait for sender to finish first (it sends the end signal)
                sender_result = await sender_task
                if not sender_result:
                    logger.error("Failed to send audio chunks")
                
                # Then wait for processing to complete
                completion = await asyncio.wait_for(receiver_processor_task, timeout=10.0)
                if completion:
                    logger.info("Successfully completed voice conversion")
                else:
                    logger.info("Voice conversion completed with errors")
            except asyncio.TimeoutError:
                logger.info("Timeout waiting for completion")
            
            # Clean up tasks
            receiver_processor_task.cancel()
            sender_task.cancel()
            
            # Wait for cancellation to complete
            for task in [receiver_processor_task, sender_task]:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Save the output audio only if requested
            if output_audio and save_output:
                output_audio_array = np.concatenate(output_audio)
                sf.write(output_path, output_audio_array, 16000)
                logger.info(f"Saved converted audio to {output_path} ({len(output_audio_array)} samples)")
        
        # 3. At the end of successful processing:
        result['success'] = True
        
        # 4. post processing 
        # merge send and receive timeline 
        merged_timeline = []
        for event in result['send_timeline']:
            merged_timeline.append({
                'timestamp': event['timestamp'],
                'cumulative_ms': event['cumulative_ms'],
                'event_type': 'send',
                'session_id': session_id
            })
        for event in result['recv_timeline']:
            merged_timeline.append({
                'timestamp': event['timestamp'],
                'cumulative_ms': event['cumulative_ms'],
                'event_type': 'recv',
                'session_id': session_id
            })
        merged_timeline.sort(key=lambda x: x['timestamp'])
        result['merged_timeline'] = merged_timeline
        
        return result
                
    except Exception as e:
        import traceback
        error_msg = f"Error during processing: {traceback.format_exc()}"
        logger.error(error_msg)
        result['error'] = error_msg
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket client for voice conversion")
    
    parser.add_argument("--source-wav-path", 
                        default="wavs/sources/low-pitched-male-24k.wav", 
                        help="Path to source audio file")
    
    parser.add_argument("--output-wav-dir", 
                        default="outputs/ws_client", 
                        help="Directory to save output audio files")
    
    parser.add_argument("--encoding",
                       choices=["PCM", "OPUS"],
                       default="PCM",
                       help="Audio encoding format (PCM or OPUS)")
    
    parser.add_argument("--samplerate", "--sr",
                       type=int,
                       choices=[8000, 12000, 16000, 24000, 48000],
                       default=16000,
                       help="Target sample rate in Hz (must be Opus compatible: 8000, 12000, 16000, 24000, 48000)")
    
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
    
    parser.add_argument("--no-real-time", 
                        action="store_true", 
                        help="Disable real-time simulation (send audio as fast as possible)")
    
    parser.add_argument("--bitrate",
                       type=int,
                       default=128000,
                       help="Bitrate for OPUS encoding (default: 128000)")
    
    parser.add_argument("--frame-duration",
                       type=int,
                       default=20,
                       help="Frame duration in ms for OPUS encoding (default: 20)")
    
    parser.add_argument("--no-save-output",
                        action="store_true",
                        help="Disable Save the output audio file after conversion")
    
    args = parser.parse_args()
    
    # Run the async function and get result
    result = asyncio.run(send_audio_file(
        websocket_url=args.url,
        api_key=args.api_key,
        real_time_simulation=not args.no_real_time,
        audio_path=args.source_wav_path,
        output_wav_dir=args.output_wav_dir,
        encoding=args.encoding,
        target_sample_rate=args.samplerate,
        chunk_time_ms=args.chunk_time,
        bitrate=args.bitrate,
        frame_duration_ms=args.frame_duration,
        save_output=not args.no_save_output,
    ))
    
    # Print the result
    print("\n" + "="*60)
    print("WEBSOCKET CLIENT RESULT")
    print("="*60)
    print(f"Success: {result['success']}")
    print(f"Session ID: {result['session_id']}")
    print(f"Send timeline events: {len(result['send_timeline'])}")
    print(f"Receive timeline events: {len(result['recv_timeline'])}")
    
    if result['send_timeline']:
        print(f"First send event: {result['send_timeline'][0]}")
        print(f"Last send event: {result['send_timeline'][-1]}")
    
    if result['recv_timeline']:
        print(f"First receive event: {result['recv_timeline'][0]}")
        print(f"Last receive event: {result['recv_timeline'][-1]}")
    
    if result['output_path']:
        print(f"Output saved to: {result['output_path']}")
    
    if result['error']:
        print(f"Error: {result['error']}")
    
    print("="*60)
    
    # Save result to JSON for inspection
    import json
    result_file = Path(args.output_wav_dir) / f"{result['session_id']}_timeline.json"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Full result saved to: {result_file}")