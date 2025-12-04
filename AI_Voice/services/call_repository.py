"""
PostgreSQL repository for persistent call storage.
Stores completed calls with conversation history and extracted fields.
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import asyncpg
from config import settings

logger = logging.getLogger(__name__)


class CallRepository:
    """PostgreSQL-backed call storage"""
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or settings.database_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Create connection pool and ensure table exists"""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10
        )
        
        # Create table if not exists
        await self._create_table()
        logger.info("CallRepository initialized")
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("CallRepository closed")
    
    async def _create_table(self):
        """Create intake_calls table if not exists"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS intake_calls (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    phone_number VARCHAR(50),
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER,
                    conversation_history JSONB NOT NULL,
                    extracted_fields JSONB,
                    salesforce_lead_id VARCHAR(50),
                    salesforce_push_status VARCHAR(20) DEFAULT 'pending',
                    salesforce_push_error TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create index on session_id for fast lookups
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_intake_calls_session_id 
                ON intake_calls(session_id)
            """)
            
            # Create index on salesforce_push_status for background job
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_intake_calls_push_status 
                ON intake_calls(salesforce_push_status)
            """)
            
            logger.info("intake_calls table ready")
    
    async def save_call(
        self,
        session_id: str,
        conversation_history: List[Dict[str, Any]],
        collected_fields: Dict[str, Any],
        phone_number: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """
        Save completed call to database.
        
        Args:
            session_id: Unique session identifier
            conversation_history: Full conversation transcript
            collected_fields: Fields collected during intake
            phone_number: Caller's phone number (if available)
            start_time: Call start time
            end_time: Call end time
            
        Returns:
            Call ID
        """
        async with self.pool.acquire() as conn:
            # Calculate duration
            duration = None
            if start_time and end_time:
                duration = int((end_time - start_time).total_seconds())
            
            # Insert call record
            row = await conn.fetchrow("""
                INSERT INTO intake_calls (
                    session_id,
                    phone_number,
                    start_time,
                    end_time,
                    duration_seconds,
                    conversation_history,
                    extracted_fields,
                    salesforce_push_status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                session_id,
                phone_number,
                start_time or datetime.utcnow(),
                end_time,
                duration,
                json.dumps(conversation_history),
                json.dumps(collected_fields),
                'pending'
            )
            
            call_id = row['id']
            logger.info(f"Saved call {session_id} to database (ID: {call_id})")
            return call_id
    
    async def get_call(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get call by session_id"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM intake_calls WHERE session_id = $1
            """, session_id)
            
            if row:
                return dict(row)
            return None
    
    async def update_salesforce_status(
        self,
        session_id: str,
        lead_id: Optional[str],
        status: str,
        error: Optional[str] = None
    ):
        """Update Salesforce push status"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE intake_calls
                SET salesforce_lead_id = $1,
                    salesforce_push_status = $2,
                    salesforce_push_error = $3,
                    updated_at = NOW()
                WHERE session_id = $4
            """,
                lead_id,
                status,
                error,
                session_id
            )
            
            logger.info(f"Updated Salesforce status for {session_id}: {status}")
    
    async def get_pending_calls(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get calls pending Salesforce push"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM intake_calls
                WHERE salesforce_push_status = 'pending'
                ORDER BY created_at ASC
                LIMIT $1
            """, limit)
            
            return [dict(row) for row in rows]
    
    async def save_call_as_json(
        self,
        session_id: str,
        conversation_history: List[Dict[str, Any]],
        collected_fields: Dict[str, Any],
        output_dir: str = "calls"
    ) -> str:
        """
        Save call to JSON file (for dev/debugging).
        
        Returns:
            Path to saved file
        """
        import os
        from pathlib import Path
        
        # Create output directory
        Path(output_dir).mkdir(exist_ok=True)
        
        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{session_id}_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)
        
        # Prepare data
        call_data = {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "conversation_history": conversation_history,
            "collected_fields": collected_fields,
            "message_count": len(conversation_history)
        }
        
        # Write to file
        with open(filepath, 'w') as f:
            json.dump(call_data, f, indent=2)
        
        logger.info(f"Saved call to JSON: {filepath}")
        return filepath
