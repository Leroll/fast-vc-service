import numpy as np
from loguru import logger
import resampy  # For high-quality resampling
import opuslib  # For opus encoding/decoding
import traceback

from fast_vc_service.session import EventType


class AudioStreamBuffer:
    """Real-time audio stream buffer for voice conversion
    
    Responsible for:
    - Accumulating audio chunks from WebSocket
    - Managing audio blocks for processing
    - Padding incomplete chunks when necessary
    - Converting between different audio formats
    """
    
    def __init__(self, session_id, 
                 # Input audio format
                 input_sample_rate=16000, input_bit_depth=16,
                 # Output audio format (for voice conversion)
                 output_sample_rate=16000, output_bit_depth=16, 
                 block_time=500, prefill_time=100):
        """Initialize the audio stream buffer
        channels are always mono (1 channel),both input and output.
        
        Args:
            session_id: Unique identifier for the session
            block_time: Standard processing block time in ms (default: 500ms)
            prefill_time: Time for first chunk processing in ms (default: 100ms)
            
            input_sample_rate: Input audio sample rate in Hz
            input_bit_depth: Input audio bit depth, which only supports 16, 24, or 32 bits
            
            output_sample_rate: Output audio sample rate in Hz (for VC processing)
            output_bit_depth: Output audio bit depth (for VC processing) 
        """
        self.session_id = session_id
        self.block_time = block_time
        self.prefill_time = prefill_time
        
        # Input format - always mono
        self.input_sample_rate = input_sample_rate
        self.input_channels = 1  # Fixed to mono
        self.input_bit_depth = input_bit_depth
        if input_bit_depth not in (16, 24, 32):
            raise ValueError(f"{session_id} | Unsupported input bit depth: {input_bit_depth}. "
                             "Supported values are 16, 24, or 32 bits.")
        
        # Calculate parameters for input format (for receiving data)
        self.input_bytes_per_frame = input_bit_depth // 8
        self.input_bytes_per_second = input_sample_rate * self.input_bytes_per_frame
        self.input_bytes_per_block = int(self.block_time / 1000 * self.input_bytes_per_second)
        self.input_bytes_per_block = self.input_bytes_per_block // self.input_bytes_per_frame * self.input_bytes_per_frame  # ensure full frames
        
        # Initialize buffer
        self.buffer = bytearray()
        self.silence_frame = b'\x00' * self.input_bytes_per_frame
        if prefill_time < block_time:  # prefill for first chunk
            padding_ms = prefill_time
            padding_bytes = int(padding_ms / 1000 * self.input_bytes_per_second)
            padding_bytes = self.silence_frame * (padding_bytes // self.input_bytes_per_frame)  # ensure full frames
            self.buffer.extend(padding_bytes)
            logger.info(f"{session_id} | Buffer pre-filled with {padding_ms}ms of silence")
            
        # Output format (for voice conversion) - always mono
        self.output_sample_rate = output_sample_rate
        self.output_channels = 1  # Fixed to mono
        self.output_bit_depth = output_bit_depth
        self.needs_conversion = self._is_needs_conversion()
        
        # 添加 session 引用用于记录事件
        self.session = None
        
    def set_session(self, session):
        """设置关联的 session 对象用于记录事件"""
        self.session = session
        
    def _is_needs_conversion(self):
        """Check if format conversion is needed
        """
        needs_resampling = self.input_sample_rate != self.output_sample_rate
        needs_bit_depth_conversion = self.input_bit_depth != self.output_bit_depth
        needs_conversion = (
            needs_resampling or 
            needs_bit_depth_conversion
        )
        if needs_conversion:
            logger.info(f"{self.session_id} | Format conversion enabled: "
                        f"SR: {self.input_sample_rate}->{self.output_sample_rate}, "
                        f"BD: {self.input_bit_depth}->{self.output_bit_depth}")
        return needs_conversion
        
    def add_chunk(self, audio_chunk: bytes):
        """Add audio chunk to buffer
        
        Args:
            audio_chunk: Raw audio bytes from WebSocket (PCM format)
        """
        # 计算音频时长并记录 send 事件
        if self.session and audio_chunk:
            chunk_duration_ms = self._calculate_chunk_duration_ms(audio_chunk)
            self.session.record_event(EventType.SEND, chunk_duration_ms)
        
        self.buffer.extend(audio_chunk)
    
    def _calculate_chunk_duration_ms(self, audio_chunk: bytes) -> float:
        """计算PCM音频块的时长（毫秒）
        
        Args:
            audio_chunk: PCM 音频数据 bytes
            
        Returns:
            float: 音频时长（毫秒）
        """
        # 根据位深度计算样本数
        samples_count = len(audio_chunk) // self.input_bytes_per_frame
        # 计算时长
        duration_ms = samples_count / self.input_sample_rate * 1000
        return duration_ms
    
    def get_buffer_duration_ms(self):
        """Get current buffer duration in milliseconds
        
        Returns:
            float: Buffer duration in ms
        """
        return len(self.buffer) / self.input_bytes_per_second * 1000
    
    def has_complete_chunk(self):
        """Check if buffer contains a complete chunk ready for processing
        
        Returns:
            bool: True if a complete chunk is available
        """
        return len(self.buffer) >= self.input_bytes_per_block
    
    def get_next_chunk(self) -> np.ndarray:
        """Extract next complete chunk from buffer
        if not enough data, padding with silence
        
        Returns:
            audio_data: pcm audio data of block_time duration for target audio format
        """
        # Check if we have enough data
        if len(self.buffer) >= self.input_bytes_per_block:
            # Extract complete chunk
            chunk = bytes(self.buffer[:self.input_bytes_per_block])
            self.buffer = self.buffer[self.input_bytes_per_block:]
        else:
            # Extract what we have
            available_bytes = len(self.buffer)
            chunk = bytes(self.buffer)
            
            # Clear buffer
            self.buffer.clear()
            
            # Calculate how many bytes we need to pad
            padding_bytes_needed = self.input_bytes_per_block - available_bytes
            
            # Pad with silence frames
            padding = self.silence_frame * ((padding_bytes_needed // len(self.silence_frame)) + 1)
            chunk = chunk + padding[:padding_bytes_needed]
            
            logger.debug(f"{self.session_id} | Padded audio chunk with {padding_bytes_needed} bytes of silence")
    
        # Convert bytes to numpy array based on input bit depth
        if self.input_bit_depth == 16:
            audio_data = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
            # Normalize to [-1, 1]
            audio_data /= 32768.0  # 2^15, normally 16-bit signed int range
        elif self.input_bit_depth == 24:
            # For 24-bit audio, handle 3-byte samples
            frames = len(chunk) // 3
            audio_data = np.zeros(frames, dtype=np.float32)
            for i in range(frames):
                # Extract 3 bytes and convert to signed 24-bit int
                bytes_val = chunk[i*3:i*3+3]
                # Extend with 0 or FF depending on sign bit
                ext_byte = b'\x00' if bytes_val[2] < 128 else b'\xff'
                val = int.from_bytes(bytes_val + ext_byte, byteorder='little', signed=True)
                audio_data[i] = val / 8388608.0  # Normalize by 2^23
        elif self.input_bit_depth == 32:
            audio_data = np.frombuffer(chunk, dtype=np.int32).astype(np.float32)
            # Normalize to [-1, 1]
            audio_data /= 2147483648.0  # 2^31
        else:
            raise ValueError(f"{self.session_id} | Unsupported bit depth: {self.input_bit_depth}")
    
        # Apply format conversion if needed
        if self.needs_conversion:
            # Resample if needed
            if self.input_sample_rate != self.output_sample_rate:
                audio_data = resampy.resample(
                    audio_data, 
                    self.input_sample_rate, 
                    self.output_sample_rate
                )
        
        return audio_data
    
    def clear(self):
        """Clear the buffer"""
        self.buffer = bytearray()


class OpusAudioStreamBuffer(AudioStreamBuffer):
    """Real-time Opus audio stream buffer for voice conversion
    
    Extends AudioStreamBuffer to handle Opus-encoded audio,
    decodes Opus packets to PCM for voice conversion processing.
    """
    
    def __init__(self, session_id, 
                 # Input audio format
                 input_sample_rate=16000,
                 # Output audio format (for voice conversion)
                 output_sample_rate=16000, output_bit_depth=16, 
                 block_time=500, prefill_time=100,
                 # opus specific parameters
                 frame_duration=20,
                 ):
        """Initialize the Opus audio stream buffer
        
        Args:
            session_id: Unique identifier for the session
            
            input_sample_rate: Input audio sample rate in Hz (must be 8000, 12000, 16000, 24000, or 48000 for Opus)
            
            output_sample_rate: Output audio sample rate for VC processing
            output_bit_depth: Output audio bit depth for VC processing
            
            block_time: Standard processing block time in ms
            prefill_time: Time for first chunk processing in ms
            
            frame_duration: Opus frame duration in ms (default: 20ms)
        """
        # Validate Opus-specific sample rates
        if input_sample_rate not in (8000, 12000, 16000, 24000, 48000):
            raise ValueError(f"{session_id} | Unsupported Opus sample rate: {input_sample_rate}. "
                           "Must be one of: 8000, 12000, 16000, 24000, or 48000 Hz.")
        
        # Initialize parent class with standard PCM settings
        # For Opus, we'll always decode to 16-bit PCM internally
        super().__init__(
            session_id=session_id,
            input_sample_rate=input_sample_rate,
            input_bit_depth=16,  # Opus decoder outputs 16-bit PCM
            output_sample_rate=output_sample_rate,
            output_bit_depth=output_bit_depth,
            block_time=block_time,
            prefill_time=prefill_time
        )
        
        # Store Opus-specific parameters
        self.opus_channels = 1
        self.frame_duration = frame_duration
        
        # Initialize Opus decoder using high-level API
        try:
            self.decoder = opuslib.Decoder(
                fs=self.input_sample_rate,
                channels=self.opus_channels
            )
            logger.info(f"{session_id} | Opus decoder initialized with sample rate {input_sample_rate}Hz, channels: {self.opus_channels}")
        except Exception as e:
            logger.error(f"{session_id} | Failed to initialize Opus decoder: \n{traceback.format_exc()}")
            raise
        
        # Calculate expected frame size for Opus (typically 20ms)
        self.opus_frame_size = int(frame_duration / 1000 * self.input_sample_rate)
        
        logger.info(f"{session_id} | Opus buffer initialized with sample rate {input_sample_rate}Hz, frame size: {self.opus_frame_size}")
    
    def add_chunk(self, opus_packet: bytes):
        """Override add_chunk to decode Opus packets before adding to buffer
        
        Args:
            opus_packet: Raw opus encoded packet from WebSocket
        """
        try:
            if not opus_packet:
                logger.warning(f"{self.session_id} | Received empty Opus packet")
                return
            
            # Decode opus packet to PCM using high-level API
            # The decoder returns bytes of int16 PCM samples
            pcm_bytes = self.decoder.decode(opus_packet, frame_size=self.opus_frame_size)
            
            # Add the decoded PCM to buffer using the parent's method
            super().add_chunk(pcm_bytes)
            
            logger.debug(f"{self.session_id} | Decoded Opus packet: {len(opus_packet)} bytes -> {len(pcm_bytes)} bytes PCM")
            
        except Exception as e:
            logger.error(f"{self.session_id} | Error decoding Opus packet: \n{traceback.format_exc()}")
            # In case of error, we could add silence instead of crashing
            silence_samples = self.opus_frame_size
            silence_bytes = b'\x00' * (silence_samples * 2)  # 2 bytes per int16 sample
            super().add_chunk(silence_bytes)
    
    def get_decoder_info(self):
        """Get information about the Opus decoder
        
        Returns:
            dict: Decoder information
        """
        return {
            "sample_rate": self.input_sample_rate,
            "channels": self.opus_channels,
            "frame_duration_ms": self.frame_duration,
            "frame_size": self.opus_frame_size,
        }
    
    def __del__(self):
        """Destructor to ensure proper cleanup"""
        try:
            if hasattr(self, 'decoder'):
                self.decoder = None
                logger.debug(f"{self.session_id} | Opus decoder cleaned up in destructor")
        except Exception as e:
            logger.error(f"{self.session_id} | Error in Opus buffer destructor: {e}")