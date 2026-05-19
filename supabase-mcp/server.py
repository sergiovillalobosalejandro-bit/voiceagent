"""
Supabase MCP Server
Provides tools for interacting with Supabase database

Environment Variables:
    SUPABASE_URL: Supabase project URL (required)
    SUPABASE_KEY: Supabase anon key or service role key (required)
"""
import os
from supabase import create_client, Client
from mcp.server.fastmcp import FastMCP

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # Can be anon key or service role key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Create MCP server
mcp = FastMCP(
    "supabase-assistant",
    instructions="Supabase assistant for database operations and storage operations",
)

@mcp.tool()
def query_table(table_name: str, columns: str = "*", filters: dict = None, limit: int = None) -> list:
    """Query a table in the Supabase database.
    Args:
        table_name: Name of the table to query
        columns: Columns to select (default: *)
        filters: Dictionary of column:value pairs for filtering
        limit: Maximum number of rows to return
    Returns:
        List of rows from the table
    """
    query = supabase.table(table_name).select(columns)

    if filters:
        for column, value in filters.items():
            query = query.eq(column, value)

    if limit:
        query = query.limit(limit)

    result = query.execute()
    return result.data

@mcp.tool()
def insert_data(table_name: str, data: dict) -> dict:
    """Insert data into a table.
    Args:
        table_name: Name of the table
        data: Dictionary of column:value pairs to insert
    Returns:
        Inserted record
    """
    result = supabase.table(table_name).insert(data).execute()
    return result.data[0] if result.data else None

@mcp.tool()
def update_data(table_name: str, data: dict, filters: dict) -> dict:
    """Update data in a table.
    Args:
        table_name: Name of the table
        data: Dictionary of column:value pairs to update
        filters: Dictionary of column:value pairs for filtering which rows to update
    Returns:
        Number of updated rows
    """
    query = supabase.table(table_name).update(data)

    for column, value in filters.items():
        query = query.eq(column, value)

    result = query.execute()
    return {"count": len(result.data)}

@mcp.tool()
def delete_data(table_name: str, filters: dict) -> dict:
    """Delete data from a table.
    Args:
        table_name: Name of the table
        filters: Dictionary of column:value pairs for filtering which rows to delete
    Returns:
        Number of deleted rows
    """
    query = supabase.table(table_name).delete()

    for column, value in filters.items():
        query = query.eq(column, value)

    result = query.execute()
    return {"count": len(result.data)}

@mcp.tool()
def call_function(function_name: str, parameters: dict = None) -> dict:
    """Call a Supabase function (stored procedure).
    Args:
        function_name: Name of the function to call
        parameters: Parameters to pass to the function
    Returns:
        Function result
    """
    if parameters:
        result = supabase.rpc(function_name, parameters).execute()
    else:
        result = supabase.rpc(function_name).execute()
    return result.data

@mcp.tool()
def upload_file(bucket_name: str, file_path: str, file_content: bytes) -> dict:
    """Upload a file to Supabase Storage.
    Args:
        bucket_name: Name of the storage bucket
        file_path: Path where the file should be stored
        file_content: File content as bytes
    Returns:
        Upload result with file information
    """
    result = supabase.storage.from_(bucket_name).upload(file_path, file_content)
    return result

@mcp.resource("supabase://tables")
def list_tables() -> list:
    """List tables in the database (requires PostgreSQL introspection)."""
    # This would require direct database access or a custom function
    # For now, return a placeholder
    return [
        {"note": "Table listing requires direct database access or custom introspection function"}
    ]

if __name__ == "__main__":
    print(f"[Supabase MCP] Starting server...")
    mcp.run(transport="stdio")