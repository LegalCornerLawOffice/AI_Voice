"""
Core audio pipeline: STT → LLM → TTS
Orchestrates conversation flow through services.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from handlers.base import AudioHandler
from services.deepgram_stt import DeepgramSTTService
from services.deepgram_tts import DeepgramTTSService
from services.bedrock_llm import BedrockLLMService
from services.structured_intake_state import StructuredIntakeState
from conversation.intake_questions import IntakeQuestionManager, IntakeQuestion
from conversation.prompts import SYSTEM_PROMPT

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
        state_manager: StructuredIntakeState,
        start_section: Optional[str] = None,
        prefilled_data: Optional[Dict[str, Any]] = None,
    ):
        self.session_id = session_id
        self.audio_handler = audio_handler
        self.state_manager = state_manager
        self.start_section = start_section  # For testing specific sections
        self.prefilled_data = prefilled_data or {}
        
        # Initialize services
        self.stt = DeepgramSTTService()
        self.tts = DeepgramTTSService()
        self.llm = BedrockLLMService()
        
        # Structured intake system
        self.question_manager = IntakeQuestionManager()
        self.current_question: Optional[IntakeQuestion] = None
        
        # State
        self.is_processing = False
        self.is_ai_speaking = False  # Track if AI is currently playing audio
        self.current_transcript = ""
        self.pending_transcripts = []  # Collect transcripts during debounce
        self.debounce_task = None  # Task for debouncing
        self.first_transcript_time = None  # Track when first transcript arrived
        
        logger.info(f"Audio pipeline initialized for session {session_id}")
    
    async def start(self) -> None:
        """Start the audio pipeline."""
        try:
            # Initialize session state with structured intake
            await self.state_manager.initialize_session(
                self.session_id,
                prefilled_data=self.prefilled_data
            )
            
            # If testing a specific section, jump to it
            if self.start_section:
                await self.state_manager.advance_section(self.session_id, self.start_section)
                logger.info(f"Starting at section: {self.start_section}")
            
            # Start STT stream with callback
            await self.stt.start_stream(
                on_transcript=self.on_transcript
            )
            
            # Send greeting (or first question if jumping to a section)
            if self.start_section:
                # Send section introduction
                section_intro = f"Hello! Today we'll be going over {self.start_section}. Let's get started."
                
                # Send intro and wait for audio to finish
                await self.state_manager.add_to_history(
                    self.session_id,
                    role="assistant",
                    content=section_intro
                )
                await self.audio_handler.send_text(f"AI: {section_intro}")
                audio = await self.tts.synthesize(section_intro)
                
                if audio:
                    self.is_ai_speaking = True
                    await self.audio_handler.send_audio(audio)
                    
                    # Calculate audio duration and wait for it to finish
                    audio_duration_seconds = len(audio) / 32000
                    await asyncio.sleep(audio_duration_seconds + 0.5)
                    self.is_ai_speaking = False
                
                # Now ask first question
                await self.ask_next_question()
            else:
                await self.send_greeting()
            
            # Process incoming audio
            async for audio_chunk in self.audio_handler.receive_audio():
                await self.stt.send_audio(audio_chunk)
            
        except Exception as e:
            logger.error(f"Error in pipeline: {e}", exc_info=True)
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
                
                # Send interrupt signal on ANY user speech (let client handle if audio is playing)
                # This ensures interrupts work even if is_ai_speaking flag has been reset
                if text.strip() and len(text.split()) >= 1:
                    if self.is_ai_speaking:
                        logger.info(f"🛑 User interrupt detected (interim: '{text}') - stopping AI audio")
                        self.is_ai_speaking = False
                    
                    # Always send interrupt to client (client will stop audio if playing)
                    if hasattr(self.audio_handler, 'websocket'):
                        await self.audio_handler.websocket.send_json({
                            "type": "interrupt",
                            "message": "User interrupt detected"
                        })
                
                return
            
            # Final result - add to pending and start/restart debounce timer
            logger.info(f"Final transcript: {text}")
            
            # Track when first transcript arrived
            import time
            current_time = time.time()
            if not self.first_transcript_time:
                self.first_transcript_time = current_time
            
            self.pending_transcripts.append(text)
            
            # Check if we've been accumulating for more than 5 seconds
            time_since_first = current_time - self.first_transcript_time
            if time_since_first >= 5.0:
                # Force processing now, don't wait for more transcripts
                logger.info(f"Max debounce time reached ({time_since_first:.1f}s), processing now")
                if self.debounce_task:
                    self.debounce_task.cancel()
                self.debounce_task = asyncio.create_task(self._process_after_debounce(force=True))
            else:
                # Cancel existing debounce task if any
                if self.debounce_task:
                    self.debounce_task.cancel()
                    try:
                        await self.debounce_task
                    except asyncio.CancelledError:
                        pass
                
                # Start new debounce task (wait 0.3 seconds for more transcripts)
                self.debounce_task = asyncio.create_task(self._process_after_debounce())
            
        except Exception as e:
            logger.error(f"Error processing transcript: {e}")
    
    async def _process_after_debounce(self, force: bool = False) -> None:
        """
        Process collected transcripts after debounce period.
        Waits 0.3 seconds to see if more transcripts arrive.
        
        Args:
            force: If True, process immediately without waiting
        """
        try:
            # Wait for debounce period unless forced
            if not force:
                await asyncio.sleep(0.3)
            
            # Skip if already processing or no transcripts
            if self.is_processing or not self.pending_transcripts:
                return
            
            self.is_processing = True
            
            # Combine all pending transcripts
            combined_text = " ".join(self.pending_transcripts)
            self.pending_transcripts.clear()
            self.first_transcript_time = None  # Reset timer
            
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
            try:
                await self.generate_response(combined_text)
            except Exception as e:
                logger.error(f"Error in generate_response: {e}", exc_info=True)
            finally:
                self.is_processing = False
            
        except asyncio.CancelledError:
            # Task was cancelled, transcripts will be processed by new task
            pass
        except Exception as e:
            logger.error(f"Error in debounce processing: {e}")
            self.is_processing = False
    
    async def _reset_speaking_after_delay(self, delay_seconds: float) -> None:
        """
        Reset is_ai_speaking flag after audio finishes playing.
        
        Args:
            delay_seconds: How long to wait (audio duration)
        """
        try:
            await asyncio.sleep(delay_seconds + 0.5)  # Add 0.5s buffer
            if self.is_ai_speaking:
                self.is_ai_speaking = False
                logger.debug("AI finished speaking")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error resetting speaking flag: {e}")
    
    def _clean_text_for_tts(self, text: str) -> str:
        """
        Clean text by removing markdown formatting before TTS.
        
        Args:
            text: Raw text from LLM (may contain markdown)
        
        Returns:
            Cleaned text suitable for TTS
        """
        import re
        
        # Remove bold/italic markdown (**text** or *text* or __text__)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
        text = re.sub(r'\*(.+?)\*', r'\1', text)      # *italic*
        text = re.sub(r'__(.+?)__', r'\1', text)      # __bold__
        text = re.sub(r'_(.+?)_', r'\1', text)        # _italic_
        
        # Remove code blocks and inline code
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)  # ```code blocks```
        text = re.sub(r'`(.+?)`', r'\1', text)                   # `inline code`
        
        # Remove markdown headers (# ## ###)
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        
        # Remove bullet points and list markers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    async def generate_response(self, user_input: str) -> None:
        """
        Process user input and handle structured intake flow.
        
        Args:
            user_input: User's transcribed speech
        """
        try:
            # Add user message to history
            await self.state_manager.add_to_history(
                self.session_id,
                role="user",
                content=user_input,
                field_api_name=self.current_question.api_name if self.current_question else None
            )
            
            # Check if we're confirming a pending value
            pending = await self.state_manager.get_pending_confirmation(self.session_id)
            
            if pending:
                # User is confirming/correcting a value
                if self._is_affirmative(user_input):
                    # Confirmed!
                    await self.state_manager.set_field_value(
                        self.session_id,
                        pending["field"],
                        pending["value"],
                        confirmed=True
                    )
                    await self.state_manager.clear_pending_confirmation(self.session_id)
                    logger.info(f"Confirmed field {pending['field']} = {pending['value']}")
                    
                    # Move to next question
                    await self.ask_next_question()
                else:
                    # User said no or provided correction
                    await self.state_manager.clear_pending_confirmation(self.session_id)
                    # Re-ask the question
                    await self.ask_next_question()
                return
            
            # Process answer to current question
            if self.current_question:
                # Validate answer
                is_valid, error_message = self.question_manager.validate_answer(
                    self.current_question,
                    user_input
                )
                
                if not is_valid:
                    # Invalid answer, ask again with error message
                    await self._send_ai_message(
                        f"{error_message} Let me ask again: {self.current_question.label}"
                    )
                    return
                
                # Store the answer
                await self.state_manager.set_field_value(
                    self.session_id,
                    self.current_question.api_name,
                    user_input,
                    confirmed=False
                )
                
                # Check if conditional logic triggered
                await self._check_conditional_triggers(self.current_question.api_name, user_input)
                
                # Check if confirmation needed
                if self.current_question.confirmation_type:
                    # Need to confirm this value
                    await self.state_manager.set_pending_confirmation(
                        self.session_id,
                        self.current_question.api_name,
                        user_input
                    )
                    # Send confirmation
                    await self._send_confirmation(self.current_question, user_input)
                else:
                    # No confirmation needed, move to next question
                    await self.ask_next_question()
            else:
                # No current question (probably after greeting)
                await self.ask_next_question()
            
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
    
    async def send_greeting(self) -> None:
        """Send initial greeting."""
        try:
            greeting = (
                "Hello, thank you for calling Legal Corner Law Office! I'm here to help gather some "
                "information about your employment situation. This will take about "
                "45 minutes to an hour. Everything you share is confidential. "
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
                
                # Calculate audio duration and schedule reset
                audio_duration_seconds = len(audio) / 32000
                asyncio.create_task(self._reset_speaking_after_delay(audio_duration_seconds))
            
            # Advance to first intake section after greeting
            first_section = self.question_manager.get_sections()[0]
            await self.state_manager.advance_section(self.session_id, first_section)
            logger.info(f"Advanced from greeting to section: {first_section}")
            
        except Exception as e:
            logger.error(f"Error sending greeting: {e}", exc_info=True)
    
    async def ask_next_question(self, is_new_section: bool = False) -> None:
        """Ask the next question in the structured intake flow."""
        try:
            # Get current state
            current_section = await self.state_manager.get_current_section(self.session_id)
            collected_fields = await self.state_manager.get_collected_fields(self.session_id)
            
            # Get next question
            question = self.question_manager.get_next_question(current_section, collected_fields)
            
            if not question:
                # Section complete, move to next section
                sections = self.question_manager.get_sections()
                current_index = sections.index(current_section)
                
                if current_index + 1 < len(sections):
                    next_section = sections[current_index + 1]
                    await self.state_manager.advance_section(self.session_id, next_section)
                    logger.info(f"Section '{current_section}' complete. Moving to '{next_section}'")
                    
                    # Send section introduction
                    section_intro = f"Great. Now we'll be moving on to {next_section}."
                    await self._send_ai_message(section_intro)
                    
                    # Get first question of new section
                    question = self.question_manager.get_next_question(next_section, collected_fields)
                else:
                    # All sections complete!
                    await self.send_closing()
                    return
            
            if not question:
                logger.error("No question found and no more sections!")
                return
            
            self.current_question = question
            
            # Check if field is pre-filled
            prefilled_value = await self.state_manager.get_prefilled_value(
                self.session_id,
                question.api_name
            )
            
            # Format question prompt
            question_text = self.question_manager.format_question_prompt(question, prefilled_value)
            
            # Add confirmation instructions if needed
            confirmation_instructions = self.question_manager.get_confirmation_instructions(question)
            
            # Build prompt for LLM
            if prefilled_value:
                # Just confirm the value
                ai_prompt = question_text
            else:
                # Ask the question
                ai_prompt = question_text
                if confirmation_instructions:
                    ai_prompt += f"\n\nIMPORTANT: {confirmation_instructions}"
            
            logger.info(f"Asking question: {question.label} (API: {question.api_name})")
            
            # Add to history
            await self.state_manager.add_to_history(
                self.session_id,
                role="assistant",
                content=ai_prompt,
                field_api_name=question.api_name
            )
            
            # Display and speak
            await self.audio_handler.send_text(f"AI: {ai_prompt}")
            audio = await self.tts.synthesize(ai_prompt)
            
            if audio:
                self.is_ai_speaking = True
                await self.audio_handler.send_audio(audio)
                
                # Calculate audio duration and schedule reset
                audio_duration_seconds = len(audio) / 32000
                asyncio.create_task(self._reset_speaking_after_delay(audio_duration_seconds))
            
        except Exception as e:
            logger.error(f"Error asking next question: {e}", exc_info=True)
    
    async def send_closing(self) -> None:
        """Send closing message when intake is complete."""
        try:
            closing = (
                "Thank you so much for taking the time to share all of this information with me. "
                "Our legal team will review everything you've told me, and someone will be in touch "
                "with you within 24 to 48 hours to discuss next steps. Is there anything else you'd "
                "like to add before we wrap up?"
            )
            
            logger.info("Sending closing message")
            
            await self.state_manager.add_to_history(
                self.session_id,
                role="assistant",
                content=closing
            )
            
            await self.audio_handler.send_text(f"AI: {closing}")
            audio = await self.tts.synthesize(closing)
            
            if audio:
                self.is_ai_speaking = True
                await self.audio_handler.send_audio(audio)
                
                audio_duration_seconds = len(audio) / 32000
                asyncio.create_task(self._reset_speaking_after_delay(audio_duration_seconds))
                
        except Exception as e:
            logger.error(f"Error sending closing: {e}", exc_info=True)
    
    def _is_affirmative(self, user_input: str) -> bool:
        """Check if user input is an affirmative response."""
        affirmatives = ["yes", "yeah", "yep", "correct", "right", "that's right", 
                       "that's correct", "yup", "uh huh", "sure"]
        user_lower = user_input.lower().strip()
        return any(affirm in user_lower for affirm in affirmatives)
    
    async def _check_conditional_triggers(self, api_name: str, value: str) -> None:
        """Check if this answer triggers conditional logic and set flags."""
        try:
            conditional_rules = self.question_manager.CONDITIONAL_RULES
            
            if api_name in conditional_rules:
                rule = conditional_rules[api_name]
                trigger_value = rule.get("triggers_when", "")
                
                # Check if value matches trigger
                if value.lower() == trigger_value.lower():
                    await self.state_manager.set_conditional_flag(
                        self.session_id,
                        api_name,
                        True
                    )
                    logger.info(f"Conditional trigger activated: {api_name} = {value}")
                else:
                    await self.state_manager.set_conditional_flag(
                        self.session_id,
                        api_name,
                        False
                    )
        except Exception as e:
            logger.error(f"Error checking conditional triggers: {e}")
    
    async def _send_confirmation(self, question: IntakeQuestion, value: str) -> None:
        """Send confirmation prompt for spelling or digit confirmation."""
        try:
            if question.confirmation_type == "spelling":
                # Confirm spelling
                confirmation_text = (
                    f"Just to confirm, you said {value}. "
                    f"Let me spell that back: {self._spell_out(value)}. "
                    f"Is that correct?"
                )
            elif question.confirmation_type == "digits":
                # Confirm digits
                confirmation_text = (
                    f"Let me confirm, you said {self._format_digits(value)}. "
                    f"Is that correct?"
                )
            else:
                # Default confirmation
                confirmation_text = f"Just to confirm, you said {value}. Is that correct?"
            
            await self._send_ai_message(confirmation_text)
            
        except Exception as e:
            logger.error(f"Error sending confirmation: {e}")
    
    def _spell_out(self, text: str) -> str:
        """Spell out text character by character."""
        # Remove special characters, keep letters and spaces
        clean = ''.join(c if c.isalnum() or c.isspace() else '' for c in text)
        # Spell each character
        return ', '.join(list(clean))
    
    def _format_digits(self, text: str) -> str:
        """Format phone number or digits for clear pronunciation."""
        # Extract just digits
        digits = ''.join(c for c in text if c.isdigit())
        
        # Format phone numbers (10 digits)
        if len(digits) == 10:
            return f"{digits[:3]}, {digits[3:6]}, {digits[6:]}"
        else:
            # Just add pauses between digits
            return ', '.join(digits)
    
    async def _send_ai_message(self, message: str) -> None:
        """Helper to send AI message via audio and text."""
        try:
            # Add to history
            await self.state_manager.add_to_history(
                self.session_id,
                role="assistant",
                content=message
            )
            
            # Display text
            await self.audio_handler.send_text(f"AI: {message}")
            
            # Synthesize and send audio
            audio = await self.tts.synthesize(message)
            
            if audio:
                self.is_ai_speaking = True
                await self.audio_handler.send_audio(audio)
                
                # Calculate audio duration and schedule reset
                audio_duration_seconds = len(audio) / 32000
                asyncio.create_task(self._reset_speaking_after_delay(audio_duration_seconds))
        
        except Exception as e:
            logger.error(f"Error sending AI message: {e}", exc_info=True)
    
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
