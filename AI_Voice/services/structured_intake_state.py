"""
Enhanced state manager for structured intake flow.
Tracks individual field collection and progress.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from services.redis_state_manager import RedisStateManager

logger = logging.getLogger(__name__)


class StructuredIntakeState(RedisStateManager):
    """Extended state manager for structured intake questions."""
    
    async def initialize_session(
        self,
        session_id: str,
        prefilled_data: Dict[str, Any] = None
    ) -> None:
        """
        Initialize session with structured intake tracking.
        
        Args:
            session_id: Unique session identifier
            prefilled_data: Pre-filled fields from case evaluation
        """
        state = {
            "session_id": session_id,
            "started_at": datetime.now().isoformat(),
            "current_section": "Client Contact Information",
            "current_question_index": 0,
            "fields": prefilled_data or {},
            "confirmed_fields": [],  # Fields that have been confirmed
            "pending_confirmation": None,  # Field waiting for confirmation
            "conversation_history": [],
            "section_progress": {},  # Track completion per section
            "conditional_flags": {},  # Track conditional logic triggers
            "last_activity": datetime.now().isoformat()
        }
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200  # 2 hour TTL
        )
        
        logger.info(f"Initialized structured intake session {session_id}")
        if prefilled_data:
            logger.info(f"  Pre-filled {len(prefilled_data)} fields: {list(prefilled_data.keys())}")
    
    async def get_prefilled_value(self, session_id: str, field_api_name: str) -> Optional[Any]:
        """Get pre-filled value for a field if it exists."""
        state = await self.get_state(session_id)
        return state.get("fields", {}).get(field_api_name)
    
    async def set_field_value(
        self,
        session_id: str,
        field_api_name: str,
        value: Any,
        confirmed: bool = False
    ) -> None:
        """
        Set a field value.
        
        Args:
            session_id: Session ID
            field_api_name: Salesforce API name (e.g., Client_Name__c)
            value: Field value
            confirmed: Whether this value has been confirmed
        """
        state = await self.get_state(session_id)
        
        state["fields"][field_api_name] = value
        state["last_activity"] = datetime.now().isoformat()
        
        if confirmed:
            if field_api_name not in state["confirmed_fields"]:
                state["confirmed_fields"].append(field_api_name)
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200
        )
        
        logger.info(f"Set field {field_api_name} = {value} (confirmed: {confirmed})")
    
    async def set_pending_confirmation(
        self,
        session_id: str,
        field_api_name: str,
        value: Any
    ) -> None:
        """Mark a field as waiting for confirmation."""
        state = await self.get_state(session_id)
        
        state["pending_confirmation"] = {
            "field": field_api_name,
            "value": value,
            "asked_at": datetime.now().isoformat()
        }
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200
        )
    
    async def get_pending_confirmation(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get field waiting for confirmation."""
        state = await self.get_state(session_id)
        return state.get("pending_confirmation")
    
    async def clear_pending_confirmation(self, session_id: str) -> None:
        """Clear pending confirmation after it's been handled."""
        state = await self.get_state(session_id)
        state["pending_confirmation"] = None
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200
        )
    
    async def set_conditional_flag(
        self,
        session_id: str,
        flag_name: str,
        value: bool
    ) -> None:
        """
        Set a conditional logic flag.
        
        Example: set_conditional_flag("has_personal_property", True)
        """
        state = await self.get_state(session_id)
        
        state["conditional_flags"][flag_name] = value
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200
        )
        
        logger.info(f"Set conditional flag {flag_name} = {value}")
    
    async def get_conditional_flag(self, session_id: str, flag_name: str) -> bool:
        """Get value of a conditional flag."""
        state = await self.get_state(session_id)
        return state.get("conditional_flags", {}).get(flag_name, False)
    
    async def advance_question(self, session_id: str) -> None:
        """Move to next question in current section."""
        state = await self.get_state(session_id)
        
        state["current_question_index"] += 1
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200
        )
    
    async def advance_section(self, session_id: str, new_section: str) -> None:
        """Move to a new section."""
        state = await self.get_state(session_id)
        
        old_section = state.get("current_section")
        state["current_section"] = new_section
        state["current_question_index"] = 0
        
        # Mark old section as complete
        if old_section:
            state["section_progress"][old_section] = "complete"
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200
        )
        
        logger.info(f"Advanced from '{old_section}' to '{new_section}'")
    
    async def get_collected_fields(self, session_id: str) -> Dict[str, Any]:
        """Get all collected field values."""
        state = await self.get_state(session_id)
        return state.get("fields", {})
    
    async def get_current_section(self, session_id: str) -> str:
        """Get current section name."""
        state = await self.get_state(session_id)
        return state.get("current_section", "Client Contact Information")
    
    async def get_section_progress(self, session_id: str) -> Dict[str, str]:
        """Get completion status of all sections."""
        state = await self.get_state(session_id)
        return state.get("section_progress", {})
    
    async def add_to_history(
        self,
        session_id: str,
        role: str,
        content: str,
        field_api_name: Optional[str] = None
    ) -> None:
        """
        Add message to conversation history.
        
        Args:
            session_id: Session ID
            role: "user" or "assistant"
            content: Message content
            field_api_name: Associated field if this message is collecting a specific field
        """
        state = await self.get_state(session_id)
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if field_api_name:
            message["field"] = field_api_name
        
        # Keep only last 20 messages to avoid context bloat
        history = state.get("conversation_history", [])
        history.append(message)
        if len(history) > 20:
            history = history[-20:]
        
        state["conversation_history"] = history
        state["last_activity"] = datetime.now().isoformat()
        
        await self.redis_client.set(
            f"session:{session_id}",
            json.dumps(state),
            ex=7200
        )
    
    async def get_recent_history(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent conversation history."""
        state = await self.get_state(session_id)
        history = state.get("conversation_history", [])
        return history[-limit:]
    
    async def get_statistics(self, session_id: str) -> Dict[str, Any]:
        """Get intake progress statistics."""
        state = await self.get_state(session_id)
        
        total_fields = len(state.get("fields", {}))
        confirmed_fields = len(state.get("confirmed_fields", []))
        sections_complete = len([s for s, status in state.get("section_progress", {}).items() if status == "complete"])
        
        return {
            "total_fields_collected": total_fields,
            "confirmed_fields": confirmed_fields,
            "current_section": state.get("current_section"),
            "sections_completed": sections_complete,
            "duration_seconds": self._calculate_duration(state),
            "last_activity": state.get("last_activity")
        }
    
    def _calculate_duration(self, state: Dict[str, Any]) -> int:
        """Calculate session duration in seconds."""
        started = datetime.fromisoformat(state.get("started_at", datetime.now().isoformat()))
        now = datetime.now()
        return int((now - started).total_seconds())
