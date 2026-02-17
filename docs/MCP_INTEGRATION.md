# MCP Integration Guide for Asset Research Agent

## Overview

The Asset Research Agent can use MCP (Model Context Protocol) servers for direct database access. This document describes how to configure the Supabase MCP server integration.

## Prerequisites

1. Supabase project with the Sparengine database schema
2. Database connection string (DATABASE_URL)
3. MCP server configured in Cursor settings or mcps folder

## Setting Up Supabase MCP Server

### 1. Install the MCP Server

The Supabase MCP server should be configured in your Cursor settings or in the `mcps/` folder.

### 2. Configure Environment Variables

Add these to your `.env` file:

```env
DATABASE_URL=postgresql://user:password@host:port/database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

### 3. Update Configuration

In `configs/config_asset_research.py`, uncomment and configure:

```python
# MCP Tools Configuration
mcp_tools = ["supabase_query", "supabase_rpc"]

mcp_tools_config = dict(
    supabase_query=dict(
        server="user-supabase",
        timeout=30
    )
)
```

## Available MCP Operations

### Query Operations

```python
# Example: Query asset metadata via MCP
result = await mcp_client.call_tool(
    server="user-supabase",
    tool_name="query",
    arguments={
        "sql": "SELECT * FROM assets WHERE id = $1",
        "params": [asset_id]
    }
)
```

### RPC Operations

```python
# Example: Call a Supabase RPC function
result = await mcp_client.call_tool(
    server="user-supabase",
    tool_name="rpc",
    arguments={
        "function": "search_similar_pages",
        "params": {"query_embedding": [...], "limit": 10}
    }
)
```

## Custom Database Tools

The Asset Research Agent also includes custom async database tools:

- `AssetMetadataTool` - Fetch asset overview
- `AssetRAGSearchTool` - Semantic search using pgvector
- `AssetPageReadTool` - Read specific pages
- `DocumentTreeTool` - Navigate document hierarchy
- `AssetBatchSummaryTool` - Get pre-computed summaries

These tools use `asyncpg` for direct database access and are configured in:
`src/tools/asset_dossier/`

## Testing the Connection

Run the test script:

```bash
python -c "
import asyncio
from src.tools.asset_dossier.db_client import SupabaseAsyncClient

async def test():
    client = await SupabaseAsyncClient.get_instance()
    result = await client.fetchrow('SELECT 1 as test')
    print('Connection successful:', result)

asyncio.run(test())
"
```

## Troubleshooting

### Connection Errors

1. Verify DATABASE_URL is set correctly
2. Check network connectivity to Supabase
3. Ensure IP is allowed in Supabase firewall settings

### Query Errors

1. Check SQL syntax matches PostgreSQL
2. Verify table and column names exist
3. Check parameter types match expected values

### MCP Server Not Found

1. Verify MCP server is installed and configured
2. Check `mcps/user-supabase/` folder exists
3. Restart Cursor IDE after configuration changes

## Security Notes

- Never commit DATABASE_URL or credentials to version control
- Use environment variables for all sensitive configuration
- Consider using row-level security (RLS) in Supabase
- Limit MCP server permissions to read-only if possible
