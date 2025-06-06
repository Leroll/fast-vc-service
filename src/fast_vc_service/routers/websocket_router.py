from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
import time
import numpy as np
import traceback
import json

from fast_vc_service.buffer import AudioStreamBuffer, OpusAudioStreamBuffer

websocket_router = APIRouter()

def validate_api_key(api_key: str) -> bool:
    """Validate the API key."""
    # TODO: Implement proper API key validation
    # This is a placeholder - replace with actual authentication logic
    return api_key is not None and len(api_key) > 0

async def send_error(websocket: WebSocket, error_code: str, message: str, session_id: str = None):
    """Send an error message to the client."""
    try:
        error_response = {
            "type": "error",
            "error_code": error_code,
            "message": message
        }
        if session_id:
            error_response["session_id"] = session_id
            
        logger.error(f"Sending error response: {error_response}")
        await websocket.send_json(error_response)
    except Exception as e:
        logger.error(f"Failed to send error message: \n{traceback.format_exc()}")

async def handle_initial_configuration(websocket: WebSocket):
    """handle the initial configuration message from the client."""

    config_data = await websocket.receive_json()
    logger.info(f"Received config data: {config_data}")
    
    # validate the configuration message
    if config_data.get("type") != "config":
        await send_error(websocket, "INVALID_CONFIG", 
                         "Expected config message type", None)
        return None, None, None
        
    # extract session ID and API key
    session_id = config_data.get("session_id")
    api_key = config_data.get("api_key")
    
    # validate API key
    if not validate_api_key(api_key):
        await send_error(websocket, "AUTH_FAILED", 
                         "Invalid API key or authentication failed", session_id)
        return None, None, None
        
    # extract audio format settings
    audio_format = config_data.get("audio_format", {})
    sample_rate = audio_format.get("sample_rate", 16000)
    bit_depth = audio_format.get("bit_depth", 16)
    channels = audio_format.get("channels", 1)
    encoding = audio_format.get("encoding", "PCM")  # supports "PCM" or "OPUS"
    
    # validate audio format settings
    if channels != 1:
        await send_error(websocket, "INVALID_CONFIG", 
                         "Only mono audio (1 channel) is supported", session_id)
        return None, None, None
    
    # create session
    realtime_vc = websocket.app.state.realtime_vc
    session = realtime_vc.create_session(session_id=session_id)
    
    # create buffer
    if encoding.upper() == "OPUS":
        frame_duration = audio_format.get("frame_duration", 20)  # Default to 20ms if not specified
        logger.info(f"{session_id} | Using Opus audio buffer.")
        buffer = OpusAudioStreamBuffer(
            session_id=session_id,
            input_sample_rate=sample_rate,
            output_sample_rate=realtime_vc.cfg.SAMPLERATE,
            output_bit_depth=realtime_vc.cfg.BIT_DEPTH,
            block_time=realtime_vc.cfg.block_time * 1000,  # Convert to milliseconds
            prefill_time=100,  # Default prefill time of 100ms
            frame_duration=frame_duration  # Opus frame duration in milliseconds
        )
    else:  # Default to PCM
        logger.info(f"{session_id} | Using PCM audio buffer.")
        buffer = AudioStreamBuffer(
            session_id=session_id,
            input_sample_rate=sample_rate,
            input_bit_depth=bit_depth,
            output_sample_rate=realtime_vc.cfg.SAMPLERATE,
            output_bit_depth=realtime_vc.cfg.BIT_DEPTH,
            block_time=realtime_vc.cfg.block_time * 1000,  # Convert to milliseconds
            prefill_time=100  # Default prefill time of 100ms
        )
    
    # send ready signal to the client
    ready_signal = {
        "type": "ready",
        "session_id": session_id,
        "message": "Ready to process audio",
    }
    await websocket.send_json(ready_signal)
    logger.info(f"{session_id} | Ready with audio format: {audio_format}")
    
    return session, buffer

async def process_new_bytes_and_vc(audio_bytes: bytes, websocket: WebSocket, buffer, session) -> int:
    """Process incoming audio bytes and return updated chunks_processed count."""
    buffer.add_chunk(audio_bytes)
    
    temp_processing_times = []
    realtime_vc = websocket.app.state.realtime_vc
    while buffer.has_complete_chunk():
        chunk_start = time.perf_counter()
    
        try:
            # Get next complete audio chunk as numpy array
            # New buffer directly returns numpy array
            numpy_chunk = buffer.get_next_chunk()
            
            realtime_vc.chunk_vc(numpy_chunk, session)
            result = session.out_data
            
            if result is None or len(result) == 0:
                logger.warning(f"{session.session_id} | No output data after voice conversion.")
                continue
            
            # Convert numpy result to bytes for sending to client
            int_data = (result * 32768.0).astype(np.int16)
            converted_bytes = int_data.tobytes()
            
            await websocket.send_bytes(converted_bytes)
            
            # Record processing metrics
            chunk_time = (time.perf_counter() - chunk_start) * 1000  # in ms
            temp_processing_times.append(chunk_time)
                
        except Exception as e:
            logger.error(f"Error processing audio chunk: \n{traceback.format_exc()}")
    
    return temp_processing_times

@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    realtime_vc = websocket.app.state.realtime_vc
    start_time = time.perf_counter()
    chunks_processed = 0
    processing_times = []
    session, buffer = None, None

    try:
        # handle initial configuration
        session, buffer = await handle_initial_configuration(websocket)
        if not session:
            return
        
        # handle audio processing
        while True:
            data = await websocket.receive()
            
            if "bytes" in data:
                audio_bytes = data["bytes"]
                if audio_bytes is None or len(audio_bytes) == 0:
                    logger.warning(f"{session.session_id} | Received empty audio bytes")
                    continue
                
                temp_processing_times = await process_new_bytes_and_vc(
                    audio_bytes, websocket, 
                    buffer, session
                )
                chunks_processed += len(temp_processing_times)
                processing_times.extend(temp_processing_times)
                
        
            elif "text" in data:
                # The JSON is already in data["text"], no need to receive again
                try:
                    json_data = json.loads(data["text"])
                    if json_data.get("type") == "end":
                        logger.info(f"{session.session_id} | Received end signal. ")
                        # 处理缓冲区中剩余的音频数据
                        while buffer.get_buffer_duration_ms() > 0:
                            logger.info(f"{session.session_id} | Processing remaining audio data. ")
                            chunk_start = time.perf_counter()
                            
                            # 获取下一个完整的音频块
                            numpy_chunk = buffer.get_next_chunk()
                            
                            result = realtime_vc.chunk_vc(numpy_chunk, session)
                            if result is not None and len(result) > 0:
                                # Convert numpy result to bytes
                                int_data = (result * 32768.0).astype(np.int16)
                                converted_bytes = int_data.tobytes()
                                
                                await websocket.send_bytes(converted_bytes)
                                
                                chunks_processed += 1
                                chunk_time = (time.perf_counter() - chunk_start) * 1000
                                processing_times.append(chunk_time)
                        
                        # save audio
                        session.save(realtime_vc.cfg.save_dir)
                        
                        # 计算统计信息
                        total_time = (time.time() - start_time) * 1000  # in ms
                        avg_latency = sum(processing_times) / len(processing_times) if processing_times else 0
                        
                        # 发送完成信号
                        await websocket.send_json({
                            "type": "complete",
                            "stats": {
                                "total_processed_ms": int(total_time),
                                "chunks_processed": chunks_processed,
                                "average_latency_ms": int(avg_latency)
                            }
                        })
                        logger.info(f"{session.session_id} | Voice conversion completed. ")
                        break
                except Exception as e:
                    logger.error(f"Error processing end signal: \n{traceback.format_exc()}")
                    await send_error(websocket, "INTERNAL_ERROR", 
                                    f"Error processing control message: {str(e)}", session.session_id)
                    break
    
    except WebSocketDisconnect:
        if session:
            logger.info(f"{session.session_id} | Client disconnected. ")
        else:
            logger.warning("Client disconnected before session was established")
    
    except Exception as e:
            logger.error(f"WebSocket error: \n{traceback.format_exc()}")
    
    finally:
        try:
            buffer.clear()
            session.cleanup()
            logger.info(f"{session.session_id} | WebSocket connection closed. ")
        except Exception as e:
            logger.error(f"Error during cleanup: \n{traceback.format_exc()}")




