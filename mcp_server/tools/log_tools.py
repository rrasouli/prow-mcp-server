"""MCP tools for log retrieval and processing."""

import re
import httpx
from typing import Dict, Any, Optional
from fastmcp import FastMCP

from ..services.gcs_service import GCSService
from ..utils.url_builder import construct_log_urls
from ..config import GCS_URL, DEFAULT_TIMEOUT


def register_log_tools(mcp: FastMCP):
    """Register log-related MCP tools."""
    
    @mcp.tool()
    async def get_build_logs(job_name: str, build_id: str, job_spec: Dict | None = None):
        """Get the logs for a specific build ID and job name.
        
        Args:
            job_name: The name of the job
            build_id: The build ID to get logs for
            job_spec: Optional job specification containing PR info
            
        Returns:
            Dictionary containing the job logs or error information
        """
        return await get_build_logs_impl(job_name, build_id, job_spec)


async def get_build_logs_impl(job_name: str, build_id: str, job_spec: Dict | None = None):
    """Internal implementation of get_build_logs that can be reused."""
    try:
        # Construct the artifacts URL and possible log URLs based on job type
        artifacts_url, possible_log_urls, pr_info = construct_log_urls(job_name, build_id, job_spec)
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=DEFAULT_TIMEOUT) as client:
            logs_found = False
            last_error = None
            
            for log_url in possible_log_urls:
                try:
                    response = await client.get(log_url)
                    
                    # Check if we got HTML (directory listing) instead of actual logs
                    content_type = response.headers.get('content-type', '').lower()
                    if 'text/html' in content_type and '<!doctype html>' in response.text:
                        # This is a directory listing, not actual logs
                        continue
                    
                    if response.status_code == 200:
                        logs = response.text
                        # Basic check to see if this looks like actual log content
                        if logs and not logs.strip().startswith('<!doctype html>'):
                            return {
                                "build_id": build_id,
                                "job_name": job_name,
                                "logs": logs,
                                "artifacts_url": artifacts_url,
                                "log_url_used": log_url
                            }
                
                except Exception as e:
                    last_error = str(e)
                    continue
            
            # If we couldn't find logs at any of the standard locations, 
            # try to parse the directory listing to find available log files
            try:
                dir_response = await client.get(artifacts_url)
                if dir_response.status_code == 200:
                    html_content = dir_response.text
                    
                    # Look for log files in the HTML directory listing
                    log_file_pattern = r'href="([^"]*\.(?:txt|log)[^"]*)"'
                    log_files = re.findall(log_file_pattern, html_content)
                    
                    if log_files:
                        # Try the first log file found
                        log_file_url = f"{artifacts_url}/{log_files[0]}"
                        log_response = await client.get(log_file_url)
                        if log_response.status_code == 200 and not log_response.text.strip().startswith('<!doctype html>'):
                            return {
                                "build_id": build_id,
                                "job_name": job_name,
                                "logs": log_response.text,
                                "artifacts_url": artifacts_url,
                                "log_url_used": log_file_url,
                                "available_log_files": log_files
                            }
                    
                    # If no specific log files found, return the directory listing with guidance
                    # Generate correct gsutil/gcloud commands based on job type
                    is_pr_job, org_repo, pr_number = pr_info
                    if is_pr_job and org_repo and pr_number:
                        base_gcs_path = f"gs://test-platform-results/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/"
                    else:
                        base_gcs_path = f"gs://test-platform-results/logs/{job_name}/{build_id}/"
                    
                    gsutil_cmd = f"gsutil -m cp -r {base_gcs_path} ."
                    gcloud_cmd = f"gcloud storage cp -r {base_gcs_path} ."
                    
                    return {
                        "build_id": build_id,
                        "job_name": job_name,
                        "error": "Could not find readable log files. Directory listing returned instead.",
                        "directory_listing": html_content,
                        "artifacts_url": artifacts_url,
                        "gsutil_command": gsutil_cmd,
                        "gcloud_command": gcloud_cmd,
                        "guidance": f"Visit the artifacts_url in a browser to manually navigate to log files, or use the provided gsutil/gcloud commands to download logs."
                    }
                    
            except Exception as parse_error:
                pass
            
            # If all attempts failed, return error information
            return {
                "error": f"Failed to fetch logs from any location. Last error: {last_error}",
                "artifacts_url": artifacts_url,
                "attempted_urls": possible_log_urls,
                "guidance": "The logs might be in a different location or format. Try accessing the artifacts_url directly."
            }
            
    except Exception as e:
        return {
            "error": f"Failed to fetch logs: {str(e)}",
            "artifacts_url": artifacts_url if 'artifacts_url' in locals() else None,
            "guidance": "Check if the build_id and job_name are correct, or try accessing logs manually."
        } 