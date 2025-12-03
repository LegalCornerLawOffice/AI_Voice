"""
Abstract base class for audio handlers.
Provides interface for receiving and sending audio from different sources (web, phone).
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator
import logging

logger = logging.getLogger(__name__)


class AudioHandler(ABC):
    """
    Abstract base class for handling audio input/output.
    
    Implementations:
    - WebRTCAudioHandler: Browser-based audio via WebRTC
    - TwilioAudioHandler: Phone calls via Twilio Media Streams
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.is_active = True
        logger.info(f"Audio handler initialized for session {session_id}")
    
    @abstractmethod
    async def receive_audio(self) -> AsyncIterator[bytes]:
        """
        Receive audio chunks from the client.
        
        Yields:
            bytes: Raw PCM audio data (16kHz, 16-bit, mono)
        """
        pass
    
    @abstractmethod
    async def send_audio(self, audio: bytes) -> None:
        """
        Send audio chunks to the client.
        
        Args:
            audio: Raw PCM audio data (16kHz, 16-bit, mono)
        """
        pass
    
    @abstractmethod
    async def send_text(self, text: str) -> None:
        """
        Send text message to client (for transcription display).
        
        Args:
            text: Text message to send
        """
        pass
    
    async def close(self) -> None:
        """Close the audio handler and cleanup resources."""
        self.is_active = False
        logger.info(f"Audio handler closed for session {self.session_id}")
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} session={self.session_id}>"
