"""Async PostgreSQL client for Sparengine database connection."""

import os
import asyncpg
from typing import Optional, List, Dict, Any
from src.utils import Singleton


class SupabaseAsyncClient(metaclass=Singleton):
    """Singleton async PostgreSQL client for Sparengine database."""
    
    _instance: Optional['SupabaseAsyncClient'] = None
    _pool: Optional[asyncpg.Pool] = None
    
    def __init__(self):
        """Initialize the client (singleton pattern)."""
        if SupabaseAsyncClient._instance is not None:
            raise RuntimeError("Use get_instance() to get the singleton instance")
        self._pool = None
    
    @classmethod
    async def get_instance(cls) -> 'SupabaseAsyncClient':
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._initialize_pool()
        return cls._instance
    
    async def _initialize_pool(self):
        """Initialize the connection pool."""
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL or SUPABASE_DATABASE_URL environment variable must be set"
            )
        
        self._pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=2,
            max_size=10,
            command_timeout=30
        )
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Execute a SELECT query and return all rows."""
        if self._pool is None:
            await self._initialize_pool()
        
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Execute a SELECT query and return one row."""
        if self._pool is None:
            await self._initialize_pool()
        
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def execute(self, query: str, *args) -> str:
        """Execute a non-SELECT query (INSERT, UPDATE, DELETE)."""
        if self._pool is None:
            await self._initialize_pool()
        
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Execute a query and return a single value."""
        if self._pool is None:
            await self._initialize_pool()
        
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
