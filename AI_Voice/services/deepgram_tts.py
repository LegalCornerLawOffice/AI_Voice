"""
Deepgram Text-to-Speech (TTS) service.
Real-time streaming speech synthesis with low latency.
"""

import asyncio
import logging
from typing import Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)


class DeepgramTTSService:
    """
    Deepgram text-to-speech service.
    
    Features:
    - Low latency synthesis
    - Natural-sounding voices
    - Streaming support
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.deepgram_api_key
        self.base_url = "https://api.deepgram.com/v1/speak"
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
        logger.info("Deepgram TTS service initialized")
    
    async def synthesize(
        self,
        text: str,
        voice: str = "aura-asteria-en",  # Professional female voice
        encoding: str = "linear16",
        sample_rate: int = 16000,
    ) -> bytes:
        """
        Synthesize text to speech.
        
        Args:
            text: Text to synthesize
            voice: Voice model to use
            encoding: Audio encoding (linear16 = PCM)
            sample_rate: Audio sample rate
        
        Returns:
            bytes: PCM audio data
        """
        try:
            params = {
                "model": voice,
                "encoding": encoding,
                "sample_rate": sample_rate,
                "container": "none",  # Raw audio
            }
            
            payload = {"text": text}
            
            response = await self.client.post(
                self.base_url,
                params=params,
                json=payload
            )
            
            if response.status_code == 200:
                audio_data = response.content
                logger.info(f"Synthesized {len(audio_data)} bytes of audio for: {text[:50]}...")
                return audio_data
            else:
                logger.error(f"Deepgram TTS error: {response.status_code} - {response.text}")
                return b""
                
        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            return b""
    
    async def synthesize_streaming(
        self,
        text: str,
        voice: str = "aura-asteria-en",
        chunk_size: int = 4096,
    ):
        """
        Stream audio synthesis (for large texts).
        
        Args:
            text: Text to synthesize
            voice: Voice model to use
            chunk_size: Size of audio chunks to yield
        
        Yields:
            bytes: Chunks of PCM audio data
        """
        try:
            params = {
                "model": voice,
                "encoding": "linear16",
                "sample_rate": 16000,
                "container": "none",
            }
            
            payload = {"text": text}
            
            async with self.client.stream(
                "POST",
                self.base_url,
                params=params,
                json=payload
            ) as response:
                if response.status_code == 200:
                    async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                        if chunk:
                            yield chunk
                else:
                    logger.error(f"Deepgram TTS streaming error: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Error in streaming synthesis: {e}")
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
        logger.info("Deepgram TTS service closed")
