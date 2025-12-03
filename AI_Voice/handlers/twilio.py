"""
Twilio audio handler for phone-based calls.
Handles audio streaming from Twilio Media Streams via WebSocket.
"""

from typing import AsyncIterator
import json
import base64
import audioop
import logging
from fastapi import WebSocket
from handlers.base import AudioHandler

logger = logging.getLogger(__name__)


class TwilioAudioHandler(AudioHandler):
    """
    Audio handler for phone calls using Twilio Media Streams.
    
    Audio format (Twilio): mu-law 8kHz, mono
    Audio format (internal): PCM 16kHz, 16-bit, mono
    Protocol: WebSocket with Twilio Media Streams messages
    
    Note: This will be implemented in Phase 2 (phone support).
    """
    
    def __init__(self, websocket: WebSocket, session_id: str):
        super().__init__(session_id)
        self.websocket = websocket
        self.stream_sid = None
        self.call_sid = None
        logger.info(f"Twilio handler initialized for session {session_id}")
    
    async def receive_audio(self) -> AsyncIterator[bytes]:
        """
        Receive audio from Twilio Media Streams.
        
        Expected message format:
        {
            "event": "media",
            "streamSid": "...",
            "media": {
                "track": "inbound",
                "chunk": "1",
                "timestamp": "...",
                "payload": "<base64-encoded-mulaw>"
            }
        }
        """
        try:
            while self.is_active:
                # Receive message from Twilio
                message = await self.websocket.receive_json()
                
                event = message.get("event")
                
                if event == "start":
                    # Stream started
                    self.stream_sid = message.get("streamSid")
                    self.call_sid = message["start"]["callSid"]
                    logger.info(f"Twilio stream started: {self.stream_sid}")
                
                elif event == "media":
                    # Audio data received
                    payload = message["media"]["payload"]
                    
                    # Decode base64 mu-law audio
                    mulaw_bytes = base64.b64decode(payload)
                    
                    # Convert mu-law to PCM (linear)
                    pcm_8khz = audioop.ulaw2lin(mulaw_bytes, 2)
                    
                    # Upsample from 8kHz to 16kHz for Deepgram
                    pcm_16khz, _ = audioop.ratecv(
                        pcm_8khz, 2, 1, 8000, 16000, None
                    )
                    
                    logger.debug(f"Received {len(pcm_16khz)} bytes of audio")
                    yield pcm_16khz
                
                elif event == "stop":
                    logger.info(f"Twilio stream stopped: {self.stream_sid}")
                    self.is_active = False
                    break
                    
        except Exception as e:
            logger.error(f"Error receiving Twilio audio: {e}")
            self.is_active = False
    
    async def send_audio(self, audio: bytes) -> None:
        """
        Send audio to Twilio Media Streams.
        
        Message format:
        {
            "event": "media",
            "streamSid": "...",
            "media": {
                "payload": "<base64-encoded-mulaw>"
            }
        }
        """
        try:
            # Downsample from 16kHz to 8kHz
            pcm_8khz, _ = audioop.ratecv(audio, 2, 1, 16000, 8000, None)
            
            # Convert PCM to mu-law
            mulaw_bytes = audioop.lin2ulaw(pcm_8khz, 2)
            
            # Encode as base64
            payload = base64.b64encode(mulaw_bytes).decode('utf-8')
            
            message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {
                    "payload": payload
                }
            }
            
            await self.websocket.send_json(message)
            logger.debug(f"Sent {len(mulaw_bytes)} bytes of mu-law audio")
        except Exception as e:
            logger.error(f"Error sending Twilio audio: {e}")
            self.is_active = False
    
    async def send_text(self, text: str) -> None:
        """
        Send text message (not applicable for Twilio voice calls).
        This is a no-op for phone calls.
        """
        logger.debug(f"Text message skipped for Twilio (voice only): {text[:50]}...")
    
    async def close(self) -> None:
        """Close Twilio stream."""
        await super().close()
        try:
            # Send stop event
            if self.stream_sid:
                await self.websocket.send_json({
                    "event": "stop",
                    "streamSid": self.stream_sid
                })
            await self.websocket.close()
        except Exception as e:
            logger.warning(f"Error closing Twilio stream: {e}")
