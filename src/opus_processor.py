import opuslib
import wave
import asyncio
from typing import Optional, Union, List, BinaryIO
import numpy as np
from aiortc.mediastreams import MediaStreamTrack, MediaStreamError
from loguru import logger

class OpusEncoder:
    """Class for encoding audio to Opus format with configurable parameters."""
    
    def __init__(self, 
                 sample_rate: int = 16000,
                 channels: int = 1, 
                 lsb_depth: int = 16,
                 application: str = "audio",
                 frame_duration: float = 20,  # in ms
                 complexity: int = 10,
                 packet_loss_percentage: int = 0):
        """Initialize the Opus encoder with the given parameters.
        
        Args:
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels
            lsb_depth: Sample depth in bits
            application: Either "audio" or "voip"
            frame_duration: Frame duration in milliseconds
            complexity: Computational complexity (0-10), higher means more CPU usage and better quality
                        0: No complexity, 10: Maximum complexity
            packet_loss_percentage: Expected packet loss percentage, higher means more error resilience 
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_duration * sample_rate // 1000   # Convert ms to samples
        self.bitrate = sample_rate * lsb_depth // 8  # Auto bitrate
        
        # Create encoder
        self.encoder = opuslib.Encoder(
            fs=sample_rate, 
            channels=channels, 
            application=application
        )
        
        # Configure encoder parameters
        self.encoder._set_lsb_depth(lsb_depth)
        self.encoder._set_complexity(complexity)
        self.encoder._set_bitrate(self.bitrate) 
        self.encoder._set_vbr(1)  # Variable bitrate
        self.encoder._set_force_channels(channels)
        self.encoder._set_packet_loss_perc(packet_loss_percentage)
    
    def encode(self, pcm_data: bytes) -> bytes:
        """Encode PCM audio data to Opus format.
        
        Args:
            pcm_data: Raw PCM audio bytes
            
        Returns:
            Encoded Opus packet
        """
        return self.encoder.encode(pcm_data, self.frame_size)
    
    def encode_file(self, input_file: str, output_file: str):
        """Encode a WAV file to Opus packets stored in a binary file.
        
        Args:
            input_file: Path to input WAV file
            output_file: Path to output file for Opus packets
        """
        with wave.open(input_file, "rb") as wav_read, open(output_file, "wb") as opus_write:
            while True:
                pcm = wav_read.readframes(self.frame_size)
                if len(pcm) == 0:
                    break
                encoded = self.encode(pcm)
                # Write packet length followed by packet data
                opus_write.write(len(encoded).to_bytes(4, byteorder='little'))
                opus_write.write(encoded)


class OpusDecoder:
    """Class for decoding Opus format to PCM audio with configurable parameters."""
    
    def __init__(self, 
                 sample_rate: int = 16000,
                 channels: int = 1,
                 frame_duration: float = 20):  
        """Initialize the Opus decoder with the given parameters.
        
        Args:
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels
            frame_size: Frame size in samples per channel, default is 20ms, which is 320 samples at 16kHz
            frame_duration: Frame duration in milliseconds,
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_duration * sample_rate // 1000  # Convert ms to samples
        
        # Create decoder
        self.decoder = opuslib.Decoder(fs=sample_rate, channels=channels)
    
    def decode(self, opus_data: bytes) -> bytes:
        """Decode Opus audio data to PCM format.
        
        Args:
            opus_data: Encoded Opus packet
            
        Returns:
            Decoded PCM audio bytes
        """
        return self.decoder.decode(opus_data, self.frame_size)
    
    def decode_file(self, input_file: str, output_file: str):
        """Decode a file containing Opus packets to a WAV file.
        
        Args:
            input_file: Path to input file with Opus packets
            output_file: Path to output WAV file
        """
        with open(input_file, "rb") as opus_read, wave.open(output_file, "wb") as wav_write:
            wav_write.setnchannels(self.channels)
            wav_write.setframerate(self.sample_rate)
            wav_write.setsampwidth(2)  # 16-bit audio
            
            while True:
                # Read packet length
                length_bytes = opus_read.read(4)
                if len(length_bytes) < 4:
                    break
                
                length = int.from_bytes(length_bytes, byteorder='little')
                opus_packet = opus_read.read(length)
                if len(opus_packet) < length:
                    break
                
                decoded = self.decode(opus_packet)
                wav_write.writeframes(decoded)


class StreamingOpusDecoder:
    """Class for streaming decoding of Opus packets, suitable for real-time applications."""
    
    def __init__(self, 
                 sample_rate: int = 16000,
                 channels: int = 1,
                 frame_duration: float = 20,
                 buffer_size: int = 10,
                 bit_depth: int = 16):
        """Initialize the streaming Opus decoder.
        
        Args:
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels
            frame_duration: Frame duration in milliseconds
            buffer_size: number of packets to buffer
            bit_depth: Bit depth of audio samples (default is 16)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_duration * sample_rate // 1000  # Convert ms to samples
        self.buffer_size = buffer_size
        self.bit_depth = bit_depth
        
        # Create decoder
        self.decoder = opuslib.Decoder(fs=sample_rate, channels=channels)
        
        # Internal buffers
        self.packet_buffer = []  # Buffer for incoming Opus packets
        self.decoded_buffer = bytearray()
        self.fec_enabled = True
        
        # Stats
        self.packets_decoded = 0  # Number of packets successfully decoded
        self.packets_lost = 0  # Number of packets lost or errored
    
    def add_packet(self, opus_data: bytes) -> None:
        """Add an Opus packet to the decoding queue.
        
        Args:
            opus_data: Encoded Opus packet
        """
        self.packet_buffer.append(opus_data)
        
        # Keep buffer at desired size
        while len(self.packet_buffer) > self.buffer_size:
            self.packet_buffer.pop(0)
    
    def decode_next(self) -> bytes:
        """Decode the next available packet in the buffer.
        
        Returns:
            Decoded PCM audio bytes or empty bytes if no packet available
        """
        if not self.packet_buffer:
            return b''
        
        opus_data = self.packet_buffer.pop(0)
        try:
            decoded = self.decoder.decode(opus_data, self.frame_size)
            self.packets_decoded += 1
            return decoded
        except Exception as e:
            logger.error(f"Error decoding packet: {e}")
            self.packets_lost += 1
            return b'\x00' * self.frame_size * self.channels * self.bit_depth // 8  # Silent frame
    
    def get_available_frames(self) -> int:
        """Get the number of frames available for decoding.
        
        Returns:
            Number of Opus packets in buffer
        """
        return len(self.packet_buffer)
    
    async def decode_stream(self, packet_generator):
        """Async method to decode a stream of packets.
        
        Args:
            packet_generator: Async generator that yields Opus packets
            
        Yields:
            Decoded PCM audio frames
        """
        async for packet in packet_generator:
            if packet:
                self.add_packet(packet)
                decoded = self.decode_next()
                if decoded:
                    yield decoded

    def handle_packet_loss(self, missing_packets: int = 1) -> bytes:
        """Handle packet loss by using FEC or concealment.
        
        Args:
            missing_packets: Number of consecutive packets lost
            
        Returns:
            Concealed audio data to fill the gap
        """
        result = bytearray()
        
        # Use FEC (Forward Error Correction) if enabled and possible
        if self.fec_enabled and self.packet_buffer and missing_packets == 1:
            try:
                # Use the next packet to reconstruct the lost one
                fec_frame = self.decoder.decode_fec(
                    self.packet_buffer[0], 
                    self.frame_size
                )
                result.extend(fec_frame)
                self.packets_lost += 1
                return bytes(result)
            except Exception as e:
                print(f"FEC failed: {e}")
        
        # Fall back to PLC (Packet Loss Concealment)
        for _ in range(missing_packets):
            try:
                plc_frame = self.decoder.decode(None, self.frame_size)
                result.extend(plc_frame)
            except:
                # If PLC fails, insert silence
                result.extend(b'\x00' * self.frame_size * self.channels * 2)
            self.packets_lost += 1
        
        return bytes(result)


class OpusStreamTrack(MediaStreamTrack):
    """MediaStreamTrack implementation for Opus audio streaming with aiortc."""
    
    kind = "audio"
    
    def __init__(self, track=None):
        super().__init__()
        self.track = track
        self.decoder = StreamingOpusDecoder()
        self._queue = asyncio.Queue()
        self._task = None
        
        if track:
            self._start()
    
    def _start(self):
        """Start processing the upstream track."""
        if self._task is None:
            self._task = asyncio.create_task(self._run_track())
    
    async def _run_track(self):
        """Process the upstream track and decode Opus packets."""
        while True:
            try:
                frame = await self.track.recv()
                # Assuming frame.data contains Opus packet
                self.decoder.add_packet(frame.data)
                decoded = self.decoder.decode_next()
                
                if decoded:
                    # Create new audio frame with decoded data
                    new_frame = frame.__class__(
                        data=decoded,
                        sample_rate=self.decoder.sample_rate,
                        sample_width=self.decoder.bit_depth // 8, 
                        channels=self.decoder.channels,
                        timestamp=frame.timestamp
                    )
                    await self._queue.put(new_frame)
            except Exception as e:
                print(f"Error in track processing: {e}")
                break
    
    async def recv(self):
        """Receive the next decoded audio frame.
        
        Returns:
            Decoded audio frame
        """
        if self.track:
            return await self._queue.get()
        else:
            # No input track, generate silence or handle accordingly
            raise MediaStreamError("No input track available")


def process_wav_file(input_file: str, output_file: str):
    """Process a WAV file through Opus encoding and decoding.
    
    Args:
        input_file: Path to input WAV file
        output_file: Path to output WAV file
    """
    # Read input WAV properties
    with wave.open(input_file, "rb") as wave_read:
        channels = wave_read.getnchannels()
        sample_rate = wave_read.getframerate()
    
    # Create encoder and decoder
    encoder = OpusEncoder(sample_rate=sample_rate, channels=channels)
    decoder = OpusDecoder(sample_rate=sample_rate, channels=channels)
    
    # Process the file
    with wave.open(input_file, "rb") as wave_read, wave.open(output_file, "wb") as wave_write:
        # Set output WAV properties
        wave_write.setnchannels(channels)
        wave_write.setframerate(sample_rate)
        wave_write.setsampwidth(2)  # 16-bit audio
        
        # Process in frames
        frame_size = int(0.02 * sample_rate)  # 20ms frames
        
        while True:
            pcm = wave_read.readframes(frame_size)
            if len(pcm) == 0:
                break
            
            # Encode and decode
            encoded = encoder.encode(pcm)
            decoded = decoder.decode(encoded)
            
            # Write to output
            wave_write.writeframes(decoded)


# Example usage
if __name__ == "__main__":
    # Process a file
    source_wav = "wavs/cases/低沉男性-YL-2025-03-14.wav"
    ouput_wav = "wavs/outputs/低沉男性-YL-2025-03-14_opus.wav"
    process_wav_file(source_wav, ouput_wav)
    print("Processing complete.")