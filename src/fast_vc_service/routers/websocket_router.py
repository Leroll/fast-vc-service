from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
import time
import numpy as np
import traceback
import json
import asyncio
from typing import Dict, Set

from fast_vc_service.buffer import AudioStreamBuffer, OpusAudioStreamBuffer
from fast_vc_service.session import Session
from fast_vc_service.adapters.protocol_detector import ProtocolDetector
from fast_vc_service.adapters.protocol_adapter import ProtocolAdapter

websocket_router = APIRouter()


class ConnectionMonitor:
    """WebSocket connection monitor."""
    
    def __init__(self):
        self._active_connections: Set[str] = set()
        self._lock = asyncio.Lock()  # 异步锁，防止并发修改
    
    async def add_connection(self, session_id: str) -> int:
        """add a new connection"""
        async with self._lock:
            self._active_connections.add(session_id)
            return len(self._active_connections)
    
    async def remove_connection(self, session_id: str) -> int:
        """remove a connection"""
        async with self._lock:
            self._active_connections.discard(session_id)
            return len(self._active_connections)
    
    async def get_connection_count(self) -> int:
        """Get the current number of active connections."""
        async with self._lock:
            return len(self._active_connections)
        
connection_monitor = ConnectionMonitor()


def validate_api_key(api_key: str) -> bool:
    """Validate the API key."""
    # 对于简单协议，接受特殊的api_key
    if api_key == "simple_protocol":
        return True
    # TODO: Implement proper API key validation
    # This is a placeholder - replace with actual authentication logic
    return api_key is not None and len(api_key) > 0


async def send_error(websocket: WebSocket, error_code: str, message: str, session_id: str = None, adapter: ProtocolAdapter = None):
    """Send an error message to the client."""
    try:
        if adapter:
            error_response = adapter.format_error_message(error_code, message, session_id or "")
        else:
            # 默认使用标准格式
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
    
    # 检测协议类型
    protocol_type = ProtocolDetector.detect(config_data)
    adapter = ProtocolDetector.get_adapter(protocol_type)
    logger.info(f"Detected protocol type: {protocol_type}")
    
    # 转换为标准格式
    standard_config = adapter.parse_init_message(config_data)
    
    # validate the configuration message
    if standard_config.get("type") != "config":
        await send_error(websocket, "INVALID_CONFIG", 
                         "Expected config message type", None, adapter)
        return None, None, None
        
    # extract session ID and API key
    session_id = standard_config.get("session_id")
    api_key = standard_config.get("api_key")
    
    # validate API key
    if not validate_api_key(api_key):
        await send_error(websocket, "AUTH_FAILED", 
                         "Invalid API key or authentication failed", session_id, adapter)
        return None, None, None
        
    # extract audio format settings
    sample_rate = standard_config.get("sample_rate", 16000)
    bit_depth = standard_config.get("bit_depth", 16)
    channels = standard_config.get("channels", 1)
    encoding = standard_config.get("encoding", "PCM")  # supports "PCM" or "OPUS"
    
    # validate audio format settings
    if channels != 1:
        await send_error(websocket, "INVALID_CONFIG", 
                         "Only mono audio (1 channel) is supported", session_id, adapter)
        return None, None, None
    
    # create session
    realtime_vc = websocket.app.state.realtime_vc
    session = realtime_vc.create_session(session_id=session_id)
    
    # create buffer
    prefill_time = websocket.app.state.cfg.buffer.prefill_time
    if encoding.upper() == "OPUS":
        # 获取OPUS帧长参数，优先级：客户端配置 > 系统配置 > 默认值20
        opus_frame_duration = standard_config.get("opus_frame_duration")
        if opus_frame_duration is None:
            opus_frame_duration = getattr(websocket.app.state.cfg.buffer, 'opus_frame_duration', 20)
        
        logger.info(f"{session_id} | Using Opus audio buffer with frame duration: {opus_frame_duration}ms")
        buffer = OpusAudioStreamBuffer(
            session_id=session_id,
            input_sample_rate=sample_rate,
            output_sample_rate=realtime_vc.cfg.SAMPLERATE,
            output_bit_depth=realtime_vc.cfg.BIT_DEPTH,
            block_time=realtime_vc.cfg.block_time * 1000,  # Convert to milliseconds
            prefill_time=prefill_time,
            frame_duration=opus_frame_duration  # Opus frame duration in milliseconds
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
            prefill_time=prefill_time
        )
    buffer.set_session(session)  # for recording send events
    
    # 根据协议决定是否发送ready消息
    if adapter.should_send_ready():
        ready_signal = {
            "type": "ready",
            "session_id": session_id,
            "message": "Ready to process audio",
        }
        await websocket.send_json(ready_signal)
        logger.info(f"{session_id} | Ready signal sent")
    else:
        logger.info(f"{session_id} | Skipping ready signal for simple protocol")
    
    current_connections = await connection_monitor.add_connection(session_id)
    logger.info(f"{session_id} | Ready with audio format: sample_rate={sample_rate}, bit_depth={bit_depth}, channels={channels}, encoding={encoding}")
    logger.info(f"{session_id} | Active connections: {current_connections}")
    
    return session, buffer, adapter


async def process_chunk(websocket: WebSocket, 
                        buffer: AudioStreamBuffer, 
                        session: Session ) -> float | None:
    """Process a single audio chunk.
    
    get the next chunk, vc, and send the result back to the client.
    """
    realtime_vc = websocket.app.state.realtime_vc
    try:
        t0 = time.perf_counter()
        # Get next complete audio chunk as numpy array
        # New buffer directly returns numpy array
        # it will pad the chunk if needed
        numpy_chunk = buffer.get_next_chunk()  
        time_msg = realtime_vc.chunk_vc(numpy_chunk, session)
        result = session.out_data
        
        if result is None or len(result) == 0:
            logger.warning(f"{session.session_id} | No output data after voice conversion.")
            return None
        
        # Convert numpy result to bytes for sending to client
        int_data = (result * 32768.0).astype(np.int16)
        converted_bytes = int_data.tobytes()
        
        await websocket.send_bytes(converted_bytes)
        
        # record output event
        output_duration_ms = len(result) / 16000 * 1000
        session.record_recv_event(output_duration_ms)
        
        # Record processing metrics
        e2e_time = (time.perf_counter() - t0) * 1000  # in ms
        time_msg = f"E2E: {e2e_time:.1f} | " + time_msg if time_msg else ""
        logger.info(f"{session.session_id} | {time_msg}")
            
    except Exception as e:
        logger.error(f"Error processing audio chunk: \n{traceback.format_exc()}")
        return None


async def process_new_bytes_and_vc(audio_bytes: bytes, 
                                   websocket: WebSocket, 
                                   buffer: AudioStreamBuffer, session: Session):
    """Process incoming audio bytes."""
    buffer.add_chunk(audio_bytes)
    
    while buffer.has_complete_chunk():
        await process_chunk(websocket, buffer, session)


async def process_tail_bytes_and_vc(websocket: WebSocket, 
                                    buffer: AudioStreamBuffer, session: Session):
    """Process remaining audio data in the buffer."""
    
    while buffer.get_buffer_duration_ms() > 0:
        logger.info(f"{session.session_id} | Processing remaining audio data: {buffer.get_buffer_duration_ms()} ms")
        await process_chunk(websocket, buffer, session)

@websocket_router.websocket("/")
@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    session, buffer, adapter = None, None, None
    receive_timeout = websocket.app.state.cfg.app.receive_timeout
    connection_added = False

    try:
        # handle initial configuration
        session, buffer, adapter = await handle_initial_configuration(websocket)
        if not session:
            return
        connection_added = True
        
        # handle audio processing
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive(),
                    timeout = receive_timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"{session.session_id} | WebSocket receive timeout after {receive_timeout} seconds")
                break
            
            if "bytes" in data:
                audio_bytes = data["bytes"]
                if audio_bytes is None or len(audio_bytes) == 0:
                    logger.warning(f"{session.session_id} | Received empty audio bytes")
                    continue
                
                await process_new_bytes_and_vc(
                    audio_bytes, websocket, 
                    buffer, session
                )
                
        
            elif "text" in data:
                try:
                    json_data = json.loads(data["text"])
                    if adapter.is_end_message(json_data):
                        logger.info(f"{session.session_id} | Received end signal. ")
                        await process_tail_bytes_and_vc(
                            websocket, buffer, session
                        )
                        
                        session.save()  # save audio
                        
                        complete_msg = adapter.format_complete_message({})  # send complete message
                        await websocket.send_json(complete_msg)
                        logger.info(f"{session.session_id} | Voice conversion completed. ")
                        
                        break
                except Exception as e:
                    logger.error(f"Error processing end signal: \n{traceback.format_exc()}")
                    await send_error(websocket, "INTERNAL_ERROR", 
                                    f"Error processing control message: {str(e)}", session.session_id, adapter)
                    break
    
    except WebSocketDisconnect:
        session_log_id = session.session_id if session else "None-ID"
        logger.info(f"{session_log_id} | Client disconnected. ")
    
    except Exception as e:
        logger.error(f"WebSocket error: \n{traceback.format_exc()}")
    
    finally:
        session_log_id = session.session_id if session else "None-ID"
        try:
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.close()
                logger.info(f"{session_log_id} | WebSocket connection closed in finally. ")
            
            if connection_added and session:
                remaining_connections = await connection_monitor.remove_connection(session.session_id)
                logger.info(f"{session_log_id} | Connection removed. Remaining active connections: {remaining_connections}")
            
            if buffer:
                buffer.clear()
            if session:
                session.save()
                session.cleanup()
            logger.info(f"{session_log_id} | Cleanup buffer and session completed. ")
                                    
        except Exception as e:
            logger.error(f"{session_log_id} | Error during cleanup: \n{traceback.format_exc()}")




