"""
Vercel MCP Server
Provides tools for interacting with Vercel API for deployments and projects

Environment Variables:
    VERCEL_TOKEN: Vercel token for authentication (required)
    VERCEL_ORG_ID: Team ID (optional, for team operations)
    VERCEL_PROJECT_ID: Project ID (optional, for project-specific operations)
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP

# Vercel configuration
VERCEL_TOKEN = os.getenv("VERCEL_TOKEN")
VERCEL_ORG_ID = os.getenv("VERCEL_ORG_ID")  # Optional, for team operations
VERCEL_PROJECT_ID = os.getenv("VERCEL_PROJECT_ID")  # Optional, for project-specific operations

if not VERCEL_TOKEN:
    raise ValueError("VERCEL_TOKEN environment variable is required")

# Vercel API configuration
VERCEL_API_BASE = "https://api.vercel.com"
HEADERS = {
    "Authorization": f"Bearer {VERCEL_TOKEN}",
    "Content-Type": "application/json",
}

# Create MCP server
mcp = FastMCP(
    "vercel-deployer",
    instructions="Vercel deployment assistant for managing projects and deployments",
)

@mcp.tool()
def list_projects() -> list:
    """List all Vercel projects for the authenticated user/team.
    Returns:
        List of projects with their details
    """
    params = {}
    if VERCEL_ORG_ID:
        params["teamId"] = VERCEL_ORG_ID

    response = httpx.get(f"{VERCEL_API_BASE}/v9/projects", headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def get_project(project_id: str = None) -> dict:
    """Get details of a specific Vercel project.
    Args:
        project_id: Project ID (if None, uses VERCEL_PROJECT_ID from env)
    Returns:
        Project details
    """
    pid = project_id or VERCEL_PROJECT_ID
    if not pid:
        raise ValueError("Project ID is required either as parameter or VERCEL_PROJECT_ID environment variable")

    response = httpx.get(f"{VERCEL_API_BASE}/v9/projects/{pid}", headers=HEADERS)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def create_deployment(
    name: str,
    files: list,
    project_id: str = None,
    target: str = "production"
) -> dict:
    """Create a new deployment.
    Args:
        name: Name for the deployment
        files: List of file objects with 'file' (path) and 'data' (base64 content) or 'data' (raw content)
        project_id: Project ID (optional, uses VERCEL_PROJECT_ID if not provided)
        target: Deployment target (production, preview, development)
    Returns:
        Deployment information
    """
    pid = project_id or VERCEL_PROJECT_ID
    if not pid:
        raise ValueError("Project ID is required")

    # Prepare deployment payload
    payload = {
        "name": name,
        "projectId": pid,
        "target": target,
        "files": []
    }

    for file_obj in files:
        file_data = {
            "file": file_obj["file"],
            "data": file_obj["data"]
        }
        payload["files"].append(file_data)

    response = httpx.post(f"{VERCEL_API_BASE}/v13/deployments", headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def get_deployment(deployment_id: str) -> dict:
    """Get details of a specific deployment.
    Args:
        deployment_id: Deployment ID
    Returns:
        Deployment details
    """
    response = httpx.get(f"{VERCEL_API_BASE}/v6/deployments/{deployment_id}", headers=HEADERS)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def list_deployments(project_id: str = None, limit: int = 10) -> list:
    """List deployments for a project.
    Args:
        project_id: Project ID (optional, uses VERCEL_PROJECT_ID if not provided)
        limit: Maximum number of deployments to return
    Returns:
        List of deployments
    """
    pid = project_id or VERCEL_PROJECT_ID
    if not pid:
        raise ValueError("Project ID is required")

    params = {"limit": limit}
    if VERCEL_ORG_ID:
        params["teamId"] = VERCEL_ORG_ID

    response = httpx.get(f"{VERCEL_API_BASE}/v6/deployments", headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def cancel_deployment(deployment_id: str) -> dict:
    """Cancel a deployment.
    Args:
        deployment_id: Deployment ID
    Returns:
        Cancellation result
    """
    response = httpx.delete(f"{VERCEL_API_BASE}/v6/deployments/{deployment_id}", headers=HEADERS)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def list_environment_variables(project_id: str = None) -> list:
    """List environment variables for a project.
    Args:
        project_id: Project ID (optional, uses VERCEL_PROJECT_ID if not provided)
    Returns:
        List of environment variables
    """
    pid = project_id or VERCEL_PROJECT_ID
    if not pid:
        raise ValueError("Project ID is required")

    params = {}
    if VERCEL_ORG_ID:
        params["teamId"] = VERCEL_ORG_ID

    response = httpx.get(f"{VERCEL_API_BASE}/v1/projects/{pid}/env", headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def create_environment_variable(
    key: str,
    value: str,
    target: str = ["production", "preview", "development"],
    project_id: str = None
) -> dict:
    """Create an environment variable.
    Args:
        key: Variable name
        value: Variable value
        target: List of deployment targets where variable should be available
        project_id: Project ID (optional, uses VERCEL_PROJECT_ID if not provided)
    Returns:
        Created environment variable
    """
    pid = project_id or VERCEL_PROJECT_ID
    if not pid:
        raise ValueError("Project ID is required")

    payload = {
        "key": key,
        "value": value,
        "target": target
    }

    params = {}
    if VERCEL_ORG_ID:
        params["teamId"] = VERCEL_ORG_ID

    response = httpx.post(f"{VERCEL_API_BASE}/v1/projects/{pid}/env", headers=HEADERS, json=payload, params=params)
    response.raise_for_status()
    return response.json()

@mcp.resource("vercel://user")
def get_user_info() -> dict:
    """Get information about the authenticated Vercel user."""
    response = httpx.get(f"{VERCEL_API_BASE}/v2/user", headers=HEADERS)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    print(f"[Vercel MCP] Starting server...")
    mcp.run(transport="stdio")