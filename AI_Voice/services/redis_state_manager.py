"""
Redis-based state manager for conversation sessions.
Replaces InMemoryStateManager for production use.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisStateManager:
    """Redis-backed conversation state manager"""
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl_hours: int = 2
    ):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_hours * 3600
        self.redis_client: Optional[redis.Redis] = None
        
    async def initialize(self):
        """Connect to Redis"""
        self.redis_client = await redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info(f"Connected to Redis at {self.redis_url}")
        
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")
    
    def _session_key(self, session_id: str) -> str:
        """Generate Redis key for session"""
        return f"session:{session_id}"
    
    async def initialize_session(
        self,
        session_id: str,
        user_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Initialize a new conversation session"""
        state = {
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "current_section": "GREETING",
            "collected_fields": user_data or {},
            "conversation_history": []
        }
        
        # Save to Redis with TTL
        key = self._session_key(session_id)
        await self.redis_client.set(
            key,
            json.dumps(state),
            ex=self.ttl_seconds
        )
        
        logger.info(f"Initialized session {session_id} in Redis")
        return state
    
    async def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation state"""
        key = self._session_key(session_id)
        data = await self.redis_client.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def update_state(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update conversation state"""
        state = await self.get_state(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")
        
        # Update fields
        state.update(updates)
        
        # Save back to Redis
        key = self._session_key(session_id)
        await self.redis_client.set(
            key,
            json.dumps(state),
            ex=self.ttl_seconds
        )
        
        return state
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ):
        """Add a message to conversation history"""
        state = await self.get_state(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        state["conversation_history"].append(message)
        
        # Save back to Redis
        key = self._session_key(session_id)
        await self.redis_client.set(
            key,
            json.dumps(state),
            ex=self.ttl_seconds
        )
    
    async def set_field(
        self,
        session_id: str,
        field_name: str,
        value: Any
    ):
        """Set a collected field value"""
        state = await self.get_state(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")
        
        state["collected_fields"][field_name] = value
        
        # Save back to Redis
        key = self._session_key(session_id)
        await self.redis_client.set(
            key,
            json.dumps(state),
            ex=self.ttl_seconds
        )
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Get conversation history"""
        state = await self.get_state(session_id)
        if not state:
            return []
        
        history = state["conversation_history"]
        if limit:
            return history[-limit:]
        return history
    
    async def set_section(
        self,
        session_id: str,
        section: str
    ):
        """Update the current conversation section"""
        state = await self.get_state(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")
        
        state["current_section"] = section
        
        # Save back to Redis
        key = self._session_key(session_id)
        await self.redis_client.set(
            key,
            json.dumps(state),
            ex=self.ttl_seconds
        )
        logger.info(f"Updated session {session_id} to section: {section}")
    
    async def end_session(
        self,
        session_id: str,
        reason: str = "completed"
    ):
        """Mark a session as ended"""
        state = await self.get_state(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")
        
        state["ended_at"] = datetime.utcnow().isoformat()
        state["end_reason"] = reason
        state["current_section"] = "COMPLETED"
        
        # Save back to Redis with extended TTL for completed sessions
        key = self._session_key(session_id)
        await self.redis_client.set(
            key,
            json.dumps(state),
            ex=self.ttl_seconds * 2  # Keep completed sessions longer
        )
        logger.info(f"Ended session {session_id}: {reason}")
    
    async def delete_session(self, session_id: str):
        """Delete a session"""
        key = self._session_key(session_id)
        await self.redis_client.delete(key)
        logger.info(f"Deleted session {session_id} from Redis")
