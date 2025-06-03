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

async def handle_initial_configuration(websocket: WebSocket, realtime_vc):
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
    
    # create a new session
    session = realtime_vc.create_session(session_id=session_id)
    
    # create appropriate audio buffer based on encoding
    if encoding.upper() == "OPUS":
        frame_duration = audio_format.get("frame_duration", 20)  # Default to 20ms if not specified
        logger.info(f"Using Opus audio buffer for session {session_id}")
        audio_buffer = OpusAudioStreamBuffer(
            session_id=session_id,
            input_sample_rate=sample_rate,
            output_sample_rate=realtime_vc.cfg.SAMPLERATE,
            output_bit_depth=realtime_vc.cfg.BIT_DEPTH,
            block_time=realtime_vc.cfg.block_time * 1000,  # Convert to milliseconds
            prefill_time=100,  # Default prefill time of 100ms
            frame_duration=frame_duration  # Opus frame duration in milliseconds
        )
    else:  # Default to PCM
        logger.info(f"Using PCM audio buffer for session {session_id}")
        audio_buffer = AudioStreamBuffer(
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
    logger.info(f"Session {session_id} is ready with audio format: {audio_format}")
    
    return session_id, session, audio_buffer

@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    realtime_vc = websocket.app.state.realtime_vc
    
    start_time = time.perf_counter()
    chunks_processed = 0
    processing_times = []

    try:
        # 处理初始配置
        session_id, session, audio_buffer = await handle_initial_configuration(websocket, realtime_vc)
        if not session:
            return
        
        # 处理音频流
        while True:
            data = await websocket.receive()
            
            # Check if it's binary data or JSON
            if "bytes" in data:
                # Process audio bytes
                audio_chunk = data["bytes"]
                if len(audio_chunk) > 0:
                    # Add audio data to buffer
                    audio_buffer.add_chunk(audio_chunk)
                    
                    # Check if there's enough data to form a complete processing block
                    while audio_buffer.has_complete_chunk():
                        chunk_start = time.perf_counter()
                        
                        # Get next complete audio chunk as numpy array
                        # New buffer directly returns numpy array
                        numpy_chunk = audio_buffer.get_next_chunk()
                        
                        # Process audio chunk
                        try:
                            # Process the audio with voice conversion
                            realtime_vc.chunk_vc(numpy_chunk, session)
                            result = session.out_data  # Get the processed output data
                            
                            # Only send when there's a result
                            if result is not None and len(result) > 0:
                                # Convert numpy result to bytes for sending to client
                                int_data = (result * 32768.0).astype(np.int16)
                                converted_bytes = int_data.tobytes()
                                
                                await websocket.send_bytes(converted_bytes)
                                
                                # Record processing metrics
                                chunks_processed += 1
                                chunk_time = (time.perf_counter() - chunk_start) * 1000  # in ms
                                processing_times.append(chunk_time)
                                
                        except Exception as e:
                            logger.error(f"Error processing audio chunk: \n{traceback.format_exc()}")
                            await send_error(websocket, "INVALID_AUDIO", 
                                           f"Error processing audio: {str(e)}", session_id)
                            break
            
            elif "text" in data:
                # The JSON is already in data["text"], no need to receive again
                try:
                    json_data = json.loads(data["text"])
                    if json_data.get("type") == "end":
                        logger.info(f"Received end signal for session {session_id}")
                        # 处理缓冲区中剩余的音频数据
                        while audio_buffer.get_buffer_duration_ms() > 0:
                            logger.info(f"Processing remaining audio data for session {session_id}")
                            chunk_start = time.perf_counter()
                            
                            # 获取下一个完整的音频块
                            numpy_chunk = audio_buffer.get_next_chunk()
                            
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
                        logger.info(f"Voice conversion completed for session {session_id}")
                        break
                except Exception as e:
                    logger.error(f"Error processing end signal: \n{traceback.format_exc()}")
                    await send_error(websocket, "INTERNAL_ERROR", 
                                    f"Error processing control message: {str(e)}", session_id)
                    break
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from WebSocket session {session_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: \n{traceback.format_exc()}")
        await send_error(websocket, "INTERNAL_ERROR", f"Server error: {str(e)}", session_id)
    
    finally:
        try:
            audio_buffer.clear()
            session.cleanup()
            logger.info(f"WebSocket connection closed for session {session_id}")
        except Exception as e:
            logger.error(f"Error during cleanup: \n{traceback.format_exc()}")




