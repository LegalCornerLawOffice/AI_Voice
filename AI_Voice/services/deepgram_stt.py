"""
Deepgram Speech-to-Text (STT) service.
Real-time streaming transcription with low latency.
NOTE: Updated for Deepgram SDK v5.3.0+ (completely new API)
"""

import asyncio
import logging
import os
import certifi
from typing import AsyncIterator, Optional, Callable
from deepgram import DeepgramClient
from deepgram.extensions.types.sockets.listen_v1_control_message import ListenV1ControlMessage
from config import settings

# Configure SSL certificates for macOS
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

logger = logging.getLogger(__name__)


class DeepgramSTTService:
    """
    Deepgram real-time speech-to-text service using SDK v5.3.0+
    
    Features:
    - Streaming transcription
    - Low latency (~300ms)
    - Automatic punctuation
    - Interim results for responsiveness
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.deepgram_api_key
        self.client = DeepgramClient(api_key=self.api_key)
        self.connection = None
        self._connection_context = None
        self._receive_task = None
        self._keepalive_task = None
        self.transcript_callback: Optional[Callable[[str, bool], None]] = None
        logger.info("Deepgram STT service initialized")
    
    async def start_stream(
        self,
        on_transcript: Callable[[str, bool], None],
        language: str = "en-US",
    ) -> None:
        """
        Start streaming transcription using Deepgram SDK v5.3.0+ API.
        
        Args:
            on_transcript: Callback function(text: str, is_final: bool)
            language: Language code (default: en-US)
        """
        try:
            self.transcript_callback = on_transcript
            
            # Connect to Deepgram v1 WebSocket API with keyword arguments (v5 SDK)
            # Note: v5 SDK's connect() returns a context manager
            # v1 API is more stable and supports more features than v2
            self._connection_context = self.client.listen.v1.connect(
                model="nova-2",
                encoding="linear16",
                sample_rate="16000",
                interim_results="true",
                smart_format="true",
                punctuate="true"
            )
            
            # Enter the context manager to get the socket client
            self.connection = self._connection_context.__enter__()
            
            # Send initial silence to prevent timeout (100ms of silence)
            # This prevents Deepgram from closing connection before audio arrives
            silence = b'\x00' * 3200  # 16kHz * 2 bytes * 0.1 sec
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.connection.send_media, silence)
            
            # Note: We don't call start_listening() because it blocks for 12+ seconds
            # The SDK should automatically start receiving once we send audio
            
            # Start receiving messages in background
            self._receive_task = asyncio.create_task(self._receive_messages())
            
            # Start keepalive task (send silence every 3 seconds to prevent timeout)
            self._keepalive_task = asyncio.create_task(self._send_keepalives())
            
            logger.info("Deepgram STT stream started")
                
        except Exception as e:
            logger.error(f"Error starting Deepgram STT: {e}")
            raise
    
    async def send_audio(self, audio_chunk: bytes) -> None:
        """
        Send audio chunk to Deepgram for transcription.
        
        Args:
            audio_chunk: PCM audio data (16kHz, 16-bit, mono)
        """
        if self.connection:
            try:
                # V1SocketClient uses send_media() method (synchronous)
                # Run in thread pool to not block event loop
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.connection.send_media, audio_chunk)
            except Exception as e:
                logger.error(f"Error sending audio to Deepgram: {e}")
    
    async def _receive_messages(self) -> None:
        """Background task to receive and process transcription results."""
        try:
            loop = asyncio.get_event_loop()
            while self.connection:
                try:
                    # Receive messages from Deepgram WebSocket in thread pool
                    # (recv() is synchronous and would block the event loop)
                    result = await loop.run_in_executor(None, self.connection.recv)
                    if result:
                        await self._on_message(result)
                except Exception as e:
                    if self.connection:  # Only log if not shutting down
                        logger.error(f"Error receiving from Deepgram: {e}")
                    break
        except asyncio.CancelledError:
            logger.info("Deepgram receive task cancelled")
        except Exception as e:
            logger.error(f"Error in Deepgram receive loop: {e}")
    
    async def _send_keepalives(self) -> None:
        """Background task to send keepalive (silence) to Deepgram."""
        try:
            silence = b'\x00' * 3200  # 100ms of silence
            loop = asyncio.get_event_loop()
            while self.connection:
                await asyncio.sleep(3)  # Send keepalive every 3 seconds
                if self.connection:
                    try:
                        # Send silence to keep connection alive (run in thread pool)
                        await loop.run_in_executor(None, self.connection.send_media, silence)
                        logger.debug("Sent keepalive silence to Deepgram")
                    except Exception as e:
                        logger.error(f"Error sending keepalive: {e}")
                        break
        except asyncio.CancelledError:
            logger.info("Deepgram keepalive task cancelled")
        except Exception as e:
            logger.error(f"Error in keepalive loop: {e}")
    
    async def _on_message(self, result) -> None:
        """Handle transcription results from Deepgram (v5 SDK format)."""
        try:
            # Check if result has transcript data
            if not hasattr(result, 'channel') or not result.channel:
                return
            
            if not result.channel.alternatives:
                return
                
            sentence = result.channel.alternatives[0].transcript
            
            if len(sentence) == 0:
                return
            
            is_final = result.is_final if hasattr(result, 'is_final') else False
            
            if self.transcript_callback:
                await self.transcript_callback(sentence, is_final)
            
            if is_final:
                logger.info(f"Final transcript: {sentence}")
            else:
                logger.debug(f"Interim transcript: {sentence}")
                
        except Exception as e:
            logger.error(f"Error processing Deepgram message: {e}")
    
    async def close(self) -> None:
        """Close Deepgram connection (v5 SDK)."""
        # Cancel background tasks
        if hasattr(self, '_receive_task') and self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if hasattr(self, '_keepalive_task') and self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        
        # Clear connection reference (will be closed by context manager)
        if self.connection:
            self.connection = None
        
        # Exit the context manager to properly close the WebSocket
        if hasattr(self, '_connection_context') and self._connection_context:
            try:
                self._connection_context.__exit__(None, None, None)
                logger.info("Deepgram STT stream closed")
            except Exception as e:
                logger.warning(f"Error exiting connection context: {e}")
            finally:
                self._connection_context = None
