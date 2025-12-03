"""
Redis-backed conversation state manager.
Tracks conversation progress, collected fields, and session state.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import redis.asyncio as redis
from config import settings

logger = logging.getLogger(__name__)


class ConversationStateManager:
    """
    Manages conversation state in Redis.
    
    Features:
    - Session-based state storage
    - Automatic expiration (2 hours)
    - Conversation history tracking
    - Field collection progress
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self.session_ttl = 7200  # 2 hours
        logger.info("Conversation state manager initialized")
    
    @classmethod
    async def create(cls):
        """Create instance with Redis connection."""
        redis_client = await redis.from_url(
            settings.redis_url,
            password=settings.redis_password,
            encoding="utf-8",
            decode_responses=True
        )
        return cls(redis_client)
    
    def _session_key(self, session_id: str) -> str:
        """Get Redis key for session."""
        return f"session:{session_id}"
    
    async def initialize_session(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize a new conversation session.
        
        Args:
            session_id: Unique session identifier
            metadata: Optional metadata (caller info, etc.)
        """
        key = self._session_key(session_id)
        
        state = {
            "session_id": session_id,
            "started_at": datetime.utcnow().isoformat(),
            "current_section": "GREETING",
            "collected_fields": {},
            "conversation_history": [],
            "metadata": metadata or {},
            "status": "active"
        }
        
        await self.redis.setex(
            key,
            self.session_ttl,
            json.dumps(state)
        )
        
        logger.info(f"Initialized session {session_id}")
    
    async def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current conversation state."""
        key = self._session_key(session_id)
        data = await self.redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def update_state(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> None:
        """
        Update conversation state.
        
        Args:
            session_id: Session identifier
            updates: Dict of fields to update
        """
        key = self._session_key(session_id)
        state = await self.get_state(session_id)
        
        if not state:
            logger.warning(f"Session {session_id} not found, creating new")
            await self.initialize_session(session_id)
            state = await self.get_state(session_id)
        
        # Merge updates
        state.update(updates)
        state["updated_at"] = datetime.utcnow().isoformat()
        
        # Save back to Redis
        await self.redis.setex(
            key,
            self.session_ttl,
            json.dumps(state)
        )
        
        logger.debug(f"Updated session {session_id}")
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> None:
        """
        Add message to conversation history.
        
        Args:
            session_id: Session identifier
            role: 'user' or 'assistant'
            content: Message content
        """
        state = await self.get_state(session_id)
        
        if state:
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            state["conversation_history"].append(message)
            
            await self.update_state(session_id, {
                "conversation_history": state["conversation_history"]
            })
            
            logger.debug(f"Added {role} message to session {session_id}")
    
    async def set_field(
        self,
        session_id: str,
        field_name: str,
        value: Any,
        confidence: float = 1.0
    ) -> None:
        """
        Set a collected field value.
        
        Args:
            session_id: Session identifier
            field_name: Salesforce field name
            value: Field value
            confidence: Confidence score (0-1)
        """
        state = await self.get_state(session_id)
        
        if state:
            state["collected_fields"][field_name] = {
                "value": value,
                "confidence": confidence,
                "collected_at": datetime.utcnow().isoformat()
            }
            
            await self.update_state(session_id, {
                "collected_fields": state["collected_fields"]
            })
            
            logger.info(f"Set field {field_name} = {value}")
    
    async def get_collected_fields(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """Get all collected fields for session."""
        state = await self.get_state(session_id)
        
        if state:
            return state.get("collected_fields", {})
        return {}
    
    async def get_conversation_history(
        self,
        session_id: str,
        format: str = "list"
    ) -> List[Dict[str, str]]:
        """
        Get conversation history.
        
        Args:
            session_id: Session identifier
            format: 'list' or 'claude' (for Claude API format)
        
        Returns:
            List of messages
        """
        state = await self.get_state(session_id)
        
        if not state:
            return []
        
        history = state.get("conversation_history", [])
        
        if format == "claude":
            # Convert to Claude API format (no timestamps)
            return [
                {"role": msg["role"], "content": msg["content"]}
                for msg in history
            ]
        
        return history
    
    async def set_section(
        self,
        session_id: str,
        section: str
    ) -> None:
        """Update current conversation section."""
        await self.update_state(session_id, {"current_section": section})
        logger.info(f"Session {session_id} moved to section {section}")
    
    async def end_session(
        self,
        session_id: str,
        reason: str = "completed"
    ) -> None:
        """Mark session as ended."""
        await self.update_state(session_id, {
            "status": reason,
            "ended_at": datetime.utcnow().isoformat()
        })
        logger.info(f"Session {session_id} ended: {reason}")
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("State manager closed")
