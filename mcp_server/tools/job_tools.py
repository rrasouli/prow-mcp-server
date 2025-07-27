"""MCP tools for job management and retrieval."""

from fastmcp import FastMCP

from ..services.prow_service import ProwService
from ..services.gcs_service import GCSService
from ..utils.url_builder import construct_log_urls


def register_job_tools(mcp: FastMCP):
    """Register job-related MCP tools."""
    
    @mcp.tool()
    async def get_latest_job_run(job_name: str):
        """Get the latest job run information from Prow for a specific job name.
        
        Args:
            job_name: The name of the Prow job to query
            
        Returns:
            Dictionary containing job information including ID, state, start time, completion time, and URL
        """
        try:
            latest_job = await ProwService.get_latest_job_for_name(job_name)
            
            if not latest_job:
                return {"error": f"No matching job found for: {job_name}"}

            status = latest_job.get("status", {})

            return {
                "job_id": latest_job["metadata"]["name"],
                "state": status.get("state"),
                "start": status.get("startTime"),
                "completion": status.get("completionTime"),
                "url": status.get("url"),
                "build_id": status.get("build_id")
            }
        except Exception as e:
            return {"error": f"Failed to fetch job info: {str(e)}"}

    @mcp.tool()
    async def get_job_logs(job_id: str):
        """Get the logs for a specific Prow job ID.
        
        Args:
            job_id: The ID of the job to get logs for
            
        Returns:
            Dictionary containing the job logs or error information
        """
        try:
            job = await ProwService.get_job_by_id(job_id)
            
            if not job:
                return {"error": f"No job found with ID: {job_id}"}

            # Get the build logs URL
            status = job.get("status", {})
            build_id = status.get("build_id")
            job_name = job.get("spec", {}).get("job")
            job_spec = job.get("spec", {})
            
            if not build_id or not job_name:
                return {"error": "Could not find build ID or job name"}

            # Use the build logs function (which will be imported from log_tools)
            from .log_tools import get_build_logs_impl
            return await get_build_logs_impl(job_name, build_id, job_spec)
                
        except Exception as e:
            return {"error": f"Failed to fetch job info: {str(e)}"}


# Helper function that can be used internally
async def get_latest_job_run_impl(job_name: str):
    """Internal implementation of get_latest_job_run."""
    latest_job = await ProwService.get_latest_job_for_name(job_name)
    
    if not latest_job:
        return {"error": f"No matching job found for: {job_name}"}

    status = latest_job.get("status", {})

    return {
        "job_id": latest_job["metadata"]["name"],
        "state": status.get("state"),
        "start": status.get("startTime"),
        "completion": status.get("completionTime"),
        "url": status.get("url"),
        "build_id": status.get("build_id")
    } 