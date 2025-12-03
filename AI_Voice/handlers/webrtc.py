"""
WebRTC audio handler for browser-based calls.
Handles audio streaming from browser via WebSocket.
"""

from typing import AsyncIterator
import json
import base64
import logging
from fastapi import WebSocket
from handlers.base import AudioHandler

logger = logging.getLogger(__name__)


class WebRTCAudioHandler(AudioHandler):
    """
    Audio handler for browser-based calls using WebRTC.
    
    Audio format: PCM 16kHz, 16-bit, mono
    Protocol: WebSocket with JSON messages
    """
    
    def __init__(self, websocket: WebSocket, session_id: str):
        super().__init__(session_id)
        self.websocket = websocket
        self.audio_queue = []
        logger.info(f"WebRTC handler initialized for session {session_id}")
    
    async def receive_audio(self) -> AsyncIterator[bytes]:
        """
        Receive audio from browser WebSocket.
        
        Expected message format:
        {
            "type": "audio",
            "data": "<base64-encoded-pcm>",
            "sampleRate": 16000
        }
        """
        try:
            while self.is_active:
                # Receive message from browser
                message = await self.websocket.receive_json()
                
                if message.get("type") == "audio":
                    # Decode base64 PCM audio
                    audio_b64 = message.get("data")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        logger.debug(f"Received {len(audio_bytes)} bytes of audio")
                        yield audio_bytes
                
                elif message.get("type") == "stop":
                    logger.info(f"Stop signal received for session {self.session_id}")
                    self.is_active = False
                    break
                    
        except Exception as e:
            logger.error(f"Error receiving audio: {e}")
            self.is_active = False
    
    async def send_audio(self, audio: bytes) -> None:
        """
        Send audio to browser WebSocket.
        
        Message format:
        {
            "type": "audio",
            "data": "<base64-encoded-pcm>",
            "sampleRate": 16000
        }
        """
        try:
            audio_b64 = base64.b64encode(audio).decode('utf-8')
            message = {
                "type": "audio",
                "data": audio_b64,
                "sampleRate": 16000
            }
            await self.websocket.send_json(message)
            logger.debug(f"Sent {len(audio)} bytes of audio")
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            self.is_active = False
    
    async def send_text(self, text: str, speaker: str = "ai") -> None:
        """
        Send text message to browser (for transcription display).
        
        Message format:
        {
            "type": "transcript",
            "text": "...",
            "speaker": "ai" or "user"
        }
        """
        try:
            message = {
                "type": "transcript",
                "text": text,
                "speaker": speaker
            }
            await self.websocket.send_json(message)
            logger.debug(f"Sent transcript: {text[:50]}...")
        except Exception as e:
            logger.error(f"Error sending text: {e}")
    
    async def close(self) -> None:
        """Close WebSocket connection."""
        await super().close()
        try:
            await self.websocket.close()
        except Exception as e:
            logger.warning(f"Error closing WebSocket: {e}")
