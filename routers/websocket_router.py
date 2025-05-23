from fastapi import APIRouter, WebSocket
from loguru import logger

from session import Session

websocket_router = APIRouter()

@websocket_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    realtime_vc = websocket.app.state.realtime_vc
    
    stream_id = None
    session = None
    try:
        # Wait for start signal
        json_data = await websocket.receive_json()
        logger.info(f"Received json data: {json_data}")
        
        if json_data.get("signal", None) != "start":
            await websocket.send_json(
                {"status": "failed", 
                 "error_msg": "Please send a start signal to begin, after that send wav bytes"}
            )
            return
        else:
            # Process start signal
            stream_id = json_data.get("stream_id", "")
            sample_rate = json_data.get("sample_rate", 16000)
            sample_bit = json_data.get("sample_bit", "16")
            
            # Create a session for this stream
            session = Session(realtime_vc, stream_id, sample_rate)
            
            await websocket.send_json({
                "status": "success",
                "message": "Ready to receive audio data",
                "stream_id": stream_id
            })
            
            # Process audio stream
            while True:
                data = await websocket.receive()
                
                # Check if it's binary data or JSON
                if "bytes" in data:
                    # Process audio bytes
                    audio_chunk = data["bytes"]
                    if len(audio_chunk) > 0:
                        # Process the audio chunk and get the converted audio
                        try:
                            converted_audio = await session.process_audio_chunk(audio_chunk)
                            if converted_audio:
                                await websocket.send_bytes(converted_audio)
                        except Exception as e:
                            logger.error(f"Error processing audio chunk: {e}")
                            await websocket.send_json({
                                "status": "failed",
                                "error_msg": f"Error processing audio: {str(e)}",
                                "stream_id": stream_id
                            })
                            break
                
                elif "text" in data:
                    # Check if it's a JSON signal
                    try:
                        end_signal = json_data = await websocket.receive_json()
                        if end_signal.get("signal") == "end":
                            # Process any remaining audio in the session
                            remaining_audio = await session.finalize()
                            if remaining_audio:
                                await websocket.send_bytes(remaining_audio)
                            
                            # Send completion signal
                            await websocket.send_json({
                                "signal": "end",
                                "status": "success",
                                "stream_id": stream_id
                            })
                            logger.info(f"Voice conversion completed for stream {stream_id}")
                            break
                    except Exception as e:
                        logger.error(f"Error processing end signal: {e}")
                        break
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "status": "failed",
                "error_msg": f"Server error: {str(e)}",
                "stream_id": stream_id
            })
        except:
            pass
    
    finally:
        if session:
            await session.cleanup()
        logger.info("WebSocket connection closed")


