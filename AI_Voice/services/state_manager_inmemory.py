"""
In-memory state manager for MVP (no Redis required)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json


class InMemoryStateManager:
    """In-memory conversation state manager for MVP"""
    
    def __init__(self, ttl_hours: int = 2):
        self.states: Dict[str, Dict[str, Any]] = {}
        self.ttl_hours = ttl_hours
        self._cleanup_task = None
        
    async def initialize(self):
        """Start the cleanup task"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
    async def close(self):
        """Stop the cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def _cleanup_loop(self):
        """Periodically clean up expired sessions"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
    
    async def _cleanup_expired(self):
        """Remove expired sessions"""
        now = datetime.utcnow()
        expired = [
            session_id 
            for session_id, state in self.states.items()
            if now - state.get("created_at", now) > timedelta(hours=self.ttl_hours)
        ]
        for session_id in expired:
            del self.states[session_id]
    
    async def initialize_session(
        self,
        session_id: str,
        user_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Initialize a new conversation session"""
        state = {
            "session_id": session_id,
            "created_at": datetime.utcnow(),
            "current_section": "GREETING",
            "collected_fields": user_data or {},
            "conversation_history": []
        }
        self.states[session_id] = state
        return state
    
    async def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation state"""
        return self.states.get(session_id)
    
    async def update_state(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update conversation state"""
        if session_id not in self.states:
            raise ValueError(f"Session {session_id} not found")
        
        state = self.states[session_id]
        state.update(updates)
        return state
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ):
        """Add a message to conversation history"""
        if session_id not in self.states:
            raise ValueError(f"Session {session_id} not found")
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.states[session_id]["conversation_history"].append(message)
    
    async def set_field(
        self,
        session_id: str,
        field_name: str,
        value: Any
    ):
        """Set a collected field value"""
        if session_id not in self.states:
            raise ValueError(f"Session {session_id} not found")
        
        self.states[session_id]["collected_fields"][field_name] = value
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Get conversation history"""
        if session_id not in self.states:
            return []
        
        history = self.states[session_id]["conversation_history"]
        if limit:
            return history[-limit:]
        return history
    
    async def delete_session(self, session_id: str):
        """Delete a session"""
        if session_id in self.states:
            del self.states[session_id]
