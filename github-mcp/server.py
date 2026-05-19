"""
GitHub MCP Server
Provides tools for interacting with GitHub API

Environment Variables:
    GITHUB_TOKEN: GitHub personal access token (required)
"""
import os
import base64
from github import Github
from mcp.server.fastmcp import FastMCP

# GitHub configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN environment variable is required")

# Initialize GitHub client
g = Github(GITHUB_TOKEN)

# Create MCP server
mcp = FastMCP(
    "github-assistant",
    instructions="GitHub assistant for managing repositories, issues, and pull requests",
)

@mcp.tool()
def list_repositories(username: str = None) -> list:
    """List repositories for a user or organization.
    Args:
        username: GitHub username or organization (if None, uses authenticated user)
    Returns:
        List of repository names and descriptions
    """
    if username:
        user = g.get_user(username)
    else:
        user = g.get_user()

    repos = []
    for repo in user.get_repos():
        repos.append({
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "url": repo.html_url,
            "stars": repo.stargazers_count,
            "language": repo.language
        })
    return repos

@mcp.tool()
def create_issue(repo_full_name: str, title: str, body: str = None, labels: list = None) -> dict:
    """Create an issue in a repository.
    Args:
        repo_full_name: Repository in format 'owner/repo'
        title: Issue title
        body: Issue description (optional)
        labels: List of label names (optional)
    Returns:
        Created issue information
    """
    repo = g.get_repo(repo_full_name)
    issue = repo.create_issue(title=title, body=body or "", labels=labels or [])
    return {
        "number": issue.number,
        "title": issue.title,
        "url": issue.html_url,
        "state": issue.state
    }

@mcp.tool()
def get_file_contents(repo_full_name: str, file_path: str, ref: str = "main") -> dict:
    """Get contents of a file from a repository.
    Args:
        repo_full_name: Repository in format 'owner/repo'
        file_path: Path to the file
        ref: Branch/tag/commit reference (default: main)
    Returns:
        File content and metadata
    """
    repo = g.get_repo(repo_full_name)
    try:
        file_content = repo.get_contents(file_path, ref=ref)
        # Decode content if it's encoded
        content = file_content.decoded_content.decode('utf-8') if file_content.encoding == 'base64' else file_content.decoded_content
        return {
            "name": file_content.name,
            "path": file_content.path,
            "content": content,
            "size": file_content.size,
            "download_url": file_content.download_url
        }
    except Exception as e:
        return {"error": f"Failed to get file: {str(e)}"}

@mcp.tool()
def search_repositories(query: str, sort: str = "stars", order: str = "desc") -> list:
    """Search for repositories.
    Args:
        query: Search query
        sort: Sort field (stars, forks, help-wanted-issues, updated)
        order: Sort order (asc, desc)
    Returns:
        List of matching repositories
    """
    repos = g.search_repositories(query=query, sort=sort, order=order)
    results = []
    for repo in repos[:10]:  # Limit to 10 results
        results.append({
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "url": repo.html_url,
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "language": repo.language
        })
    return results

@mcp.resource("github://user")
def get_current_user() -> dict:
    """Get the currently authenticated GitHub user."""
    user = g.get_user()
    return {
        "login": user.login,
        "name": user.name,
        "public_repos": user.public_repos,
        "followers": user.followers,
        "following": user.following
    }

if __name__ == "__main__":
    print(f"[GitHub MCP] Starting server...")
    mcp.run(transport="stdio")