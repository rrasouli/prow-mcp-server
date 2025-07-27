"""Tools for PR-related operations in the MCP Prow server."""

import asyncio
import json
from typing import List, Dict, Any, Optional

from fastmcp import FastMCP
from ..config import get_default_org_repo, get_default_job_name, GCS_URL
from ..services.pr_finder import smart_pr_build_finder
from ..utils.pr_parser import extract_pr_info


def register_pr_tools(mcp: FastMCP) -> None:
    """Register PR-related tools with the MCP server."""

    @mcp.tool()
    def find_pr_for_prow_job(
        job_id: str,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None
    ) -> str:
        """
        Find the PR number and details associated with a specific Prow job.
        
        Args:
            job_id: The Prow job ID to look up
            org_repo: Organization and repository (e.g., 'redhat-developer_rhdh'). Uses default if not provided.
            job_name: Job name pattern. Uses default if not provided.
            
        Returns:
            JSON string with PR details including number, title, author, and links
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
        if job_name is None:
            job_name = get_default_job_name()
            
        try:
            # For now, return a placeholder result since we don't have the actual implementation
            # In a real implementation, this would query Prow API for job details
            result = {
                "success": True,
                "job_id": job_id,
                "org_repo": org_repo,
                "job_name": job_name,
                "note": "This tool needs implementation - placeholder for PR lookup by job ID"
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to find PR details: {str(e)}",
                "job_id": job_id,
                "org_repo": org_repo,
                "job_name": job_name
            }
            return json.dumps(error_result, indent=2)

    @mcp.tool()
    def get_latest_prow_build_for_pr(
        pr_number: str,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None
    ) -> str:
        """
        Find the latest Prow build ID for a specific GitHub PR number.
        
        Args:
            pr_number: The GitHub PR number (e.g., "3191")
            org_repo: Organization and repository (e.g., 'redhat-developer_rhdh'). Uses default if not provided.
            job_name: Job name pattern. Uses default if not provided.
            
        Returns:
            JSON string with build information including build_id, job_name, pr_number, etc.
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
        if job_name is None:
            job_name = get_default_job_name()
            
        try:
            # Run the async function using asyncio
            result = asyncio.run(smart_pr_build_finder(pr_number, org_repo, job_name))
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to find PR build: {str(e)}",
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name
            }
            return json.dumps(error_result, indent=2)

    @mcp.tool()
    def get_recent_job_status(
        pr_number: int,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        Get recent job status for a specific PR across multiple runs.
        
        Args:
            pr_number: The PR number to check
            org_repo: Organization and repository (e.g., 'redhat-developer_rhdh'). Uses default if not provided.
            job_name: Job name pattern. Uses default if not provided.
            limit: Maximum number of recent jobs to return (default: 10)
            
        Returns:
            JSON string with recent job statuses and trends
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
        if job_name is None:
            job_name = get_default_job_name()
            
        try:
            # This is a placeholder for actual implementation
            # In a real implementation, this would query Prow for recent job runs
            result = {
                "success": True,
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name,
                "recent_jobs": [],
                "note": "This tool needs implementation - placeholder for recent job status lookup"
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to get recent job status: {str(e)}",
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name
            }
            return json.dumps(error_result, indent=2) 