"""MongoDB connection and collections management."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from bson.codec_options import CodecOptions
from bson.binary import UuidRepresentation

from orchestrator.config import settings


class Database:
    """Centralized MongoDB connection manager."""
    
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    async def connect(cls) -> None:
        """Initialize MongoDB connection."""
        if cls.client is None:
            cls.client = AsyncIOMotorClient(
                settings.mongodb_uri,
                uuidRepresentation='standard'
            )
            cls.db = cls.client[settings.mongodb_db]
            
            # Create indexes for better query performance
            await cls._create_indexes()
    
    @classmethod
    async def disconnect(cls) -> None:
        """Close MongoDB connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
    
    @classmethod
    async def _create_indexes(cls) -> None:
        """Create database indexes."""
        if cls.db is None:
            return
        
        # Users collection indexes
        # Note: username index is sparse, so None values won't cause duplicates
        try:
            await cls.db.users.create_index("username", unique=True, sparse=True)
        except Exception:
            pass  # Index might already exist
        await cls.db.users.create_index("created_at")
        
        # Conversations collection indexes
        await cls.db.conversations.create_index("user_id")
        await cls.db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
        
        # Messages collection indexes
        await cls.db.messages.create_index("conversation_id")
        await cls.db.messages.create_index([("conversation_id", 1), ("timestamp", 1)])
        await cls.db.messages.create_index("user_id")
        
        # Analysis history collection indexes
        await cls.db.analysis_history.create_index("user_id")
        await cls.db.analysis_history.create_index("message_id")
        await cls.db.analysis_history.create_index([("user_id", 1), ("created_at", -1)])
    
    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """Get database instance."""
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db


# Convenience accessors for collections
def get_users_collection():
    """Get users collection."""
    return Database.get_db().users


def get_conversations_collection():
    """Get conversations collection."""
    return Database.get_db().conversations


def get_messages_collection():
    """Get messages collection."""
    return Database.get_db().messages


def get_analysis_history_collection():
    """Get analysis history collection."""
    return Database.get_db().analysis_history
