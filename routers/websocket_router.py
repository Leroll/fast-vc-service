from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
import time

from session import Session

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
        logger.error(f"Failed to send error message: {e}")


async def handle_initial_configuration(websocket: WebSocket, realtime_vc):
    """handle the initial configuration message from the client."""

    config_data = await websocket.receive_json()
    logger.info(f"Received config data: {config_data}")
    
    # validate the configuration message
    if config_data.get("type") != "config":
        await send_error(websocket, "INVALID_CONFIG", 
                         "Expected config message type", None)
        return None, None
        
    # extract session ID and API key
    session_id = config_data.get("session_id")
    api_key = config_data.get("api_key")
    
    # validate API key
    if not validate_api_key(api_key):
        await send_error(websocket, "AUTH_FAILED", 
                         "Invalid API key or authentication failed", session_id)
        return None, None
        
    # extract audio format settings
    audio_format = config_data.get("audio_format", {})
    sample_rate = audio_format.get("sample_rate", 16000)
    bit_depth = audio_format.get("bit_depth", 16)
    channels = audio_format.get("channels", 1)
    encoding = audio_format.get("encoding", "PCM")
    
    # validate audio format settings
    if channels != 1:
        await send_error(websocket, "INVALID_CONFIG", 
                         "Only mono audio (1 channel) is supported", session_id)
        return None, None
        
    # create a new session
    session = realtime_vc.create_session(session_id=session_id)
    
    # send ready signal to the client
    ready_signal = {
        "type": "ready",
        "session_id": session_id,
        "message": "Ready to process audio",
    }
    await websocket.send_json(ready_signal)
    logger.info(f"Session {session_id} is ready with audio format: {audio_format}")
    
    return session_id, session


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
        session_id, session = await handle_initial_configuration(websocket, realtime_vc)
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
                    chunk_start = time.time()
                    
                    # Process the audio chunk and get the converted audio
                    try:
                        converted_audio = await session.process_audio_chunk(audio_chunk)
                        if converted_audio:
                            await websocket.send_bytes(converted_audio)
                            
                        # Track processing metrics
                        chunks_processed += 1
                        chunk_time = (time.time() - chunk_start) * 1000  # in ms
                        processing_times.append(chunk_time)
                        
                    except Exception as e:
                        logger.error(f"Error processing audio chunk: {e}")
                        await send_error(websocket, "INVALID_AUDIO", 
                                        f"Error processing audio: {str(e)}", session_id)
                        break
            
            elif "text" in data:
                # Check if it's a JSON signal
                try:
                    json_data = await websocket.receive_json()
                    if json_data.get("type") == "end":
                        # Process any remaining audio in the session
                        remaining_audio = await session.finalize()
                        if remaining_audio:
                            await websocket.send_bytes(remaining_audio)
                        
                        # Calculate statistics
                        total_time = (time.time() - start_time) * 1000  # in ms
                        avg_latency = sum(processing_times) / len(processing_times) if processing_times else 0
                        
                        # Send completion signal
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
                    logger.error(f"Error processing end signal: {e}")
                    await send_error(websocket, "INTERNAL_ERROR", 
                                    f"Error processing control message: {str(e)}", session_id)
                    break
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from WebSocket session {session_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await send_error(websocket, "INTERNAL_ERROR", f"Server error: {str(e)}", session_id)
    
    finally:
        if session:
            await session.cleanup()
        logger.info(f"WebSocket connection closed for session {session_id}")



