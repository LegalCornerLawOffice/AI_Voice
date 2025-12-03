"""
Core audio pipeline: STT → LLM → TTS
Orchestrates conversation flow through services.
"""

import asyncio
import logging
from typing import Optional
from handlers.base import AudioHandler
from services.deepgram_stt import DeepgramSTTService
from services.deepgram_tts import DeepgramTTSService
from services.bedrock_llm import BedrockLLMService
from services.state_manager_inmemory import InMemoryStateManager
from conversation.flow import ConversationFlow
from conversation.prompts import build_conversation_prompt

logger = logging.getLogger(__name__)


class AudioPipeline:
    """
    Core audio processing pipeline.
    
    Flow:
    1. Receive audio from handler
    2. Transcribe with Deepgram STT
    3. Process with Bedrock LLM
    4. Synthesize with Deepgram TTS
    5. Send audio back to handler
    """
    
    def __init__(
        self,
        session_id: str,
        audio_handler: AudioHandler,
        state_manager: InMemoryStateManager,
    ):
        self.session_id = session_id
        self.audio_handler = audio_handler
        self.state_manager = state_manager
        
        # Initialize services
        self.stt = DeepgramSTTService()
        self.tts = DeepgramTTSService()
        self.llm = BedrockLLMService()
        
        # Conversation flow
        self.flow = ConversationFlow()
        
        # State
        self.is_processing = False
        self.is_ai_speaking = False  # Track if AI is currently playing audio
        self.current_transcript = ""
        self.pending_transcripts = []  # Collect transcripts during debounce
        self.debounce_task = None  # Task for debouncing
        
        logger.info(f"Audio pipeline initialized for session {session_id}")
    
    async def start(self) -> None:
        """Start the audio pipeline."""
        try:
            # Initialize session state
            await self.state_manager.initialize_session(self.session_id)
            
            # Start STT stream with callback
            await self.stt.start_stream(
                on_transcript=self.on_transcript
            )
            
            # Send greeting
            await self.send_greeting()
            
            # Process incoming audio
            async for audio_chunk in self.audio_handler.receive_audio():
                await self.stt.send_audio(audio_chunk)
            
        except Exception as e:
            logger.error(f"Error in pipeline: {e}")
        finally:
            await self.cleanup()
    
    async def on_transcript(self, text: str, is_final: bool) -> None:
        """
        Handle transcript from STT.
        
        Args:
            text: Transcribed text
            is_final: Whether this is final or interim result
        """
        try:
            if not is_final:
                # Interim result - just display
                self.current_transcript = text
                await self.audio_handler.send_text(f"[You]: {text}", speaker="user")
                
                # If AI is speaking and user starts talking, it's an interrupt
                if self.is_ai_speaking and len(text.split()) >= 2:
                    logger.info("User interrupt detected - stopping AI audio")
                    self.is_ai_speaking = False
                    # Send interrupt signal to client
                    if hasattr(self.audio_handler, 'websocket'):
                        await self.audio_handler.websocket.send_json({
                            "type": "interrupt",
                            "message": "User interrupt detected"
                        })
                
                return
            
            # Final result - add to pending and start/restart debounce timer
            logger.info(f"Final transcript: {text}")
            self.pending_transcripts.append(text)
            
            # Cancel existing debounce task if any
            if self.debounce_task:
                self.debounce_task.cancel()
                try:
                    await self.debounce_task
                except asyncio.CancelledError:
                    pass
            
            # Start new debounce task (wait 1.5 seconds for more transcripts)
            self.debounce_task = asyncio.create_task(self._process_after_debounce())
            
        except Exception as e:
            logger.error(f"Error processing transcript: {e}")
    
    async def _process_after_debounce(self) -> None:
        """
        Process collected transcripts after debounce period.
        Waits 1.5 seconds to see if more transcripts arrive.
        """
        try:
            # Wait for debounce period
            await asyncio.sleep(1.0)
            
            # Skip if already processing or no transcripts
            if self.is_processing or not self.pending_transcripts:
                return
            
            self.is_processing = True
            
            # Combine all pending transcripts
            combined_text = " ".join(self.pending_transcripts)
            self.pending_transcripts.clear()
            
            logger.info(f"Processing combined transcript: {combined_text}")
            
            # Add to conversation history
            await self.state_manager.add_message(
                self.session_id,
                role="user",
                content=combined_text
            )
            
            # Display user's message
            await self.audio_handler.send_text(f"You: {combined_text}", speaker="user")
            
            # Generate AI response
            await self.generate_response(combined_text)
            
            self.is_processing = False
            
        except asyncio.CancelledError:
            # Task was cancelled, transcripts will be processed by new task
            pass
        except Exception as e:
            logger.error(f"Error in debounce processing: {e}")
            self.is_processing = False
    
    async def generate_response(self, user_input: str) -> None:
        """
        Generate AI response based on user input.
        
        Args:
            user_input: User's transcribed speech
        """
        try:
            # Get current state
            state = await self.state_manager.get_state(self.session_id)
            current_section = state.get("current_section", "GREETING")
            collected_fields = state.get("collected_fields", {})
            
            # Get conversation history
            history = await self.state_manager.get_conversation_history(
                self.session_id
            )
            
            # Build prompt
            system_prompt = build_conversation_prompt(
                section=current_section,
                collected_fields=collected_fields,
                conversation_history=history
            )
            
            # Format messages for Bedrock (remove timestamp field)
            bedrock_messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in history
            ]
            
            # Generate response from LLM
            response = await self.llm.generate(
                messages=bedrock_messages,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=500
            )
            
            ai_text = response["content"]
            
            logger.info(f"AI response: {ai_text}")
            
            # Add to history
            await self.state_manager.add_message(
                self.session_id,
                role="assistant",
                content=ai_text
            )
            
            # Display AI's message
            await self.audio_handler.send_text(f"AI: {ai_text}")
            
            # Synthesize and send audio
            audio = await self.tts.synthesize(ai_text)
            
            if audio:
                self.is_ai_speaking = True
                await self.audio_handler.send_audio(audio)
                # Note: is_ai_speaking will be set to False when user interrupts
                # or we can add a callback when audio finishes playing
            
            # Check if should advance section
            await self.check_section_progress(collected_fields)
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
    
    async def send_greeting(self) -> None:
        """Send initial greeting."""
        try:
            greeting = (
                "Hello, thank you for calling. I'm here to help gather some "
                "information about your employment situation. This will take about "
                "30 to 45 minutes. Everything you share is confidential. "
                "Are you ready to begin?"
            )
            
            logger.info("Sending greeting")
            
            # Add to history
            await self.state_manager.add_message(
                self.session_id,
                role="assistant",
                content=greeting
            )
            
            # Display and speak
            await self.audio_handler.send_text(f"AI: {greeting}")
            audio = await self.tts.synthesize(greeting)
            
            if audio:
                self.is_ai_speaking = True
                await self.audio_handler.send_audio(audio)
            
        except Exception as e:
            logger.error(f"Error sending greeting: {e}")
    
    async def check_section_progress(
        self,
        collected_fields: dict
    ) -> None:
        """Check if current section is complete and advance if needed."""
        try:
            state = await self.state_manager.get_state(self.session_id)
            current_section = state.get("current_section", "GREETING")
            
            # Check if section is complete
            if self.flow.is_section_complete(current_section, collected_fields):
                # Get next section
                next_section = self.flow.get_next_section(
                    current_section,
                    collected_fields
                )
                
                if next_section:
                    await self.state_manager.set_section(
                        self.session_id,
                        next_section
                    )
                    logger.info(f"Advanced to section: {next_section}")
                else:
                    # Conversation complete
                    await self.state_manager.end_session(
                        self.session_id,
                        reason="completed"
                    )
                    logger.info("Conversation completed")
                    
        except Exception as e:
            logger.error(f"Error checking section progress: {e}")
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        try:
            # Cancel debounce task if running
            if self.debounce_task:
                self.debounce_task.cancel()
                try:
                    await self.debounce_task
                except asyncio.CancelledError:
                    pass
            
            await self.stt.close()
            await self.tts.close()
            logger.info("Pipeline cleanup complete")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
