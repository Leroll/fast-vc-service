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
from pydantic import BaseModel
from enum import Enum

class EncodingEnum(Enum):
    PCM = "PCM"
    OPUS = "OPUS"
    
class SampleRateEnum(Enum):
    SR_8000 = 8000
    SR_12000 = 12000
    SR_16000 = 16000
    SR_24000 = 24000
    SR_48000 = 48000
    
class SessionIDTypeEnum(Enum):
    FILENAME = "filename"  # use filename as session ID
    TIMESTAMP = "timestamp"  # generate session ID with timestamp prefix

class Inputs(BaseModel):
    # server params
    url: str = "ws://localhost:8042/ws"  # WebSocket URL
    api_key: str = "test-key"  # API key for authentication
    
    # concurrency params
    max_workers: int = 2  # Maximum number of parallel websocket clients
    worker_delay: float = 1.0  # Delay in seconds between starting each worker
    
    # wav params
    src_wavs: list = ["resources/srcs/female-0-16khz.wav"]   # List of source wav file paths
    session_id_type: SessionIDTypeEnum  = SessionIDTypeEnum.TIMESTAMP  # Type of session ID to generate  
    output_wav_dir: str = "outputs/ws_client"  # Directory to save output audio files
    real_time: bool = True  # Simulate real-time audio sending, if False, send as fast as possible
    
    # encoding params
    encoding: EncodingEnum = EncodingEnum.PCM  # Audio encoding format (PCM or OPUS)
    samplerate: SampleRateEnum = SampleRateEnum.SR_16000  # Target sample rate in Hz (must be Opus compatible: 8000, 12000, 16000, 24000, 48000)
    # pcm params
    chunk_time: int = 20  # Chunk time in ms for sending audio (default: 20ms)
    # opus params
    bitrate: int = 128000  # Bitrate for OPUS encoding (default: 128000)
    frame_duration: int = 20  # Frame duration in ms for OPUS encoding (default: 20)
    
    # results params
    save_timeline: bool = False  # Save send/receive timeline to JSON file
    
 
def generate_session_id(stype: SessionIDTypeEnum, wav_path: str):
    """
    Generate a session ID based on the specified type.
    """
    unique_suffix = uuid.uuid4().hex[:6]  # 取UUID的前4位保证唯一性
    
    if stype == SessionIDTypeEnum.FILENAME:
        return f"{Path(wav_path).stem}-{unique_suffix}"
    elif stype == SessionIDTypeEnum.TIMESTAMP:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")    
        return f"F{timestamp}-{unique_suffix}"
    else:
        raise ValueError(f"Unsupported session ID type: {stype}")
        
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
                          session_id_type: SessionIDTypeEnum = SessionIDTypeEnum.TIMESTAMP,
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
        session_id = generate_session_id(session_id_type, audio_path)
        result['session_id'] = session_id
        
        # Generate output path based on input filename
        Path(output_wav_dir).mkdir(parents=True, exist_ok=True)
        output_path = Path(output_wav_dir).joinpath(f"{session_id}__ws-client.wav").as_posix()
        result['output_path'] = str(output_path)
        
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
        async with websockets.connect(
            websocket_url,
            ping_interval=600,   
            ping_timeout=600,    
            close_timeout=600,  
            max_size=None,
        ) as websocket:
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
            # 取消 10 秒超时，改为无限等待
            response = await websocket.recv()
            response_data = json.loads(response)
            if response_data.get("type") != "ready":
                logger.info(f"Error: Unexpected response: {response_data}")
                return result
            logger.info(f"Server ready: {response_data.get('message')}")
            
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
                
                # 取消动态超时，改为无限等待接收完成
                completion = await receiver_processor_task
                if completion:
                    logger.info("Successfully completed voice conversion")
                else:
                    logger.info("Voice conversion completed with errors")
            except asyncio.CancelledError:
                logger.info("Cancelled while waiting for completion.")
            
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
            if output_audio:
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


async def run_ws_client_async(inputs, idx):
    src_wav = inputs.src_wavs[idx]

    result = await send_audio_file(
        websocket_url=inputs.url,
        api_key=inputs.api_key,

        audio_path=src_wav,
        session_id_type=inputs.session_id_type,
        output_wav_dir=inputs.output_wav_dir,
        real_time_simulation=inputs.real_time,
        
        encoding=inputs.encoding.value,
        target_sample_rate=inputs.samplerate.value,
        chunk_time_ms=inputs.chunk_time,
        bitrate=inputs.bitrate,
        frame_duration_ms=inputs.frame_duration,
    )
    return result
    

def process_result(result, save_timeline=False, output_wav_dir="outputs/ws_client"):
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
    if save_timeline:
        result_file = Path(output_wav_dir) / f"{result['session_id']}_timeline.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Full result saved to: {result_file}")
        

async def multi_ws_clients(inputs: Inputs):
    # semaphore controls max concurrent clients
    sem = asyncio.Semaphore(max(1, inputs.max_workers))

    async def worker(idx: int):
        async with sem:
            return await run_ws_client_async(inputs, idx)

    tasks = []
    for idx in range(len(inputs.src_wavs)):
        tasks.append(asyncio.create_task(worker(idx)))
        if inputs.worker_delay > 0:
            await asyncio.sleep(inputs.worker_delay)  # stagger start

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(f"Worker {idx} failed: {res}")
            # build a minimal error result for printing
            err_result = {
                'success': False,
                'session_id': (inputs.session_ids[idx] if not inputs.session_gen else None),
                'send_timeline': [],
                'recv_timeline': [],
                'output_path': None,
                'error': str(res),
            }
            process_result(err_result, inputs.save_timeline, inputs.output_wav_dir)
        else:
            process_result(res, inputs.save_timeline, inputs.output_wav_dir)
            
def get_inputs_example():
    """
    Example
    """
    src_dir = "resources/srcs"
    src_wavs = [ str(p) for p in Path(src_dir).glob("*.wav") ]
    logger.info(f"Found {len(src_wavs)} source wav files in {src_dir}")
    session_id_type = SessionIDTypeEnum.FILENAME
    
    max_workers = min(10, len(src_wavs))  # 10并发
    worker_delay = 0.1
    return Inputs(src_wavs=src_wavs, session_id_type=session_id_type,
                  max_workers=max_workers, worker_delay=worker_delay)

def get_inputs():
    """
    Customer your own input parameters here.
    """
    return get_inputs_example()  # demo    
    


if __name__ == "__main__":
    """
    Usage:
        cd fast-vc-service
        uv run examples/websocket/ws_client.py
        
    you can also modify the get_inputs() function to customize your own input parameters.
    """
    inputs = get_inputs()
    asyncio.run(multi_ws_clients(inputs))