"""
AWS Bedrock LLM service using Claude 3.5 Sonnet.
Handles conversation logic and field extraction.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
import boto3
from botocore.config import Config
from config import settings

logger = logging.getLogger(__name__)


class BedrockLLMService:
    """
    AWS Bedrock LLM service using Claude 3.5 Sonnet.
    
    Features:
    - Structured conversation management
    - Field extraction for intake forms
    - Streaming responses
    - HIPAA-compliant
    """
    
    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
    ):
        self.model_id = model_id or settings.aws_bedrock_model_id
        self.region = region or settings.aws_region
        
        # Configure boto3 client
        config = Config(
            region_name=self.region,
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )
        
        self.client = boto3.client(
            'bedrock-runtime',
            config=config,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        
        logger.info(f"Bedrock LLM service initialized with model {self.model_id}")
    
    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Generate response from Claude.
        
        Args:
            messages: List of conversation messages [{"role": "user", "content": "..."}]
            system_prompt: System prompt for behavior
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
        
        Returns:
            Dict with 'content' (response text) and 'stop_reason'
        """
        try:
            # Build request payload
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            # Make synchronous call (wrap in executor for async)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(payload)
                )
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            content = response_body['content'][0]['text']
            stop_reason = response_body.get('stop_reason', 'end_turn')
            
            logger.info(f"Generated response ({len(content)} chars)")
            logger.debug(f"Response: {content[:200]}...")
            
            return {
                "content": content,
                "stop_reason": stop_reason,
                "usage": response_body.get('usage', {})
            }
            
        except Exception as e:
            logger.error(f"Error generating from Bedrock: {e}")
            raise
    
    async def generate_streaming(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        """
        Stream response from Claude token by token.
        
        Args:
            messages: Conversation messages
            system_prompt: System prompt
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
        
        Yields:
            str: Text chunks as they're generated
        """
        try:
            # Build request payload
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            # Make streaming call
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.invoke_model_with_response_stream(
                    modelId=self.model_id,
                    body=json.dumps(payload)
                )
            )
            
            # Stream response chunks
            stream = response['body']
            for event in stream:
                chunk = event.get('chunk')
                if chunk:
                    chunk_data = json.loads(chunk['bytes'])
                    
                    if chunk_data['type'] == 'content_block_delta':
                        delta = chunk_data['delta']
                        if delta.get('type') == 'text_delta':
                            text = delta.get('text', '')
                            if text:
                                yield text
            
            logger.info("Streaming generation complete")
            
        except Exception as e:
            logger.error(f"Error streaming from Bedrock: {e}")
            raise
    
    async def extract_fields(
        self,
        transcript: str,
        fields_schema: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        Extract structured fields from conversation transcript.
        
        Args:
            transcript: Current user statement
            fields_schema: Schema of fields to extract
            conversation_history: Previous conversation context
        
        Returns:
            Dict of extracted field values
        """
        try:
            # Build extraction prompt
            system_prompt = """You are a legal intake specialist extracting information from client conversations.
Extract relevant field values from the conversation. Only include fields that are clearly stated.
Return a JSON object with field names as keys and extracted values."""
            
            user_message = f"""
Conversation history:
{json.dumps(conversation_history, indent=2)}

Current statement: {transcript}

Fields to extract:
{json.dumps(fields_schema, indent=2)}

Extract any mentioned field values as JSON:
"""
            
            messages = [{"role": "user", "content": user_message}]
            
            response = await self.generate(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for extraction
            )
            
            # Parse JSON from response
            content = response['content']
            
            # Try to extract JSON from response
            try:
                # Look for JSON block in markdown
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                else:
                    json_str = content.strip()
                
                extracted = json.loads(json_str)
                logger.info(f"Extracted {len(extracted)} fields")
                return extracted
                
            except json.JSONDecodeError:
                logger.warning("Failed to parse extraction JSON")
                return {}
            
        except Exception as e:
            logger.error(f"Error extracting fields: {e}")
            return {}
