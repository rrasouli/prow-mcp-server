"""Service for interacting with GCS storage and retrieving logs/artifacts."""

import re
from typing import List, Optional, Dict, Any
import httpx

from ..config import GCS_URL, DEFAULT_TIMEOUT


class GCSService:
    """Service class for GCS storage interactions."""
    
    @staticmethod
    async def get_builds_for_job(job_name: str) -> List[str]:
        """Get all build IDs for a specific job from GCS.
        
        Args:
            job_name: The name of the job
            
        Returns:
            List of build IDs sorted by number (newest first)
        """
        logs_url = f"{GCS_URL}/logs/{job_name}"
        
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(logs_url)
                if response.status_code == 200:
                    html_content = response.text
                    build_pattern = r'<a href="(\d+)/"'
                    builds = re.findall(build_pattern, html_content)
                    return sorted(builds, key=int, reverse=True)
        except Exception:
            pass
        
        return []
    
    @staticmethod
    async def get_pr_builds(org_repo: str, pr_number: str, job_name: str) -> List[str]:
        """Get all build IDs for a specific PR from GCS PR logs structure.
        
        Args:
            org_repo: Organization and repository in format "org_repo"
            pr_number: The PR number
            job_name: The name of the job
            
        Returns:
            List of build IDs sorted by number (newest first)
        """
        pr_logs_url = f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}"
        
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(pr_logs_url)
                if response.status_code == 200:
                    html_content = response.text
                    build_pattern = r'<a href="(\d+)/"'
                    builds = re.findall(build_pattern, html_content)
                    return sorted(builds, key=int, reverse=True)
        except Exception:
            pass
        
        return []
    
    @staticmethod
    async def get_build_metadata(job_name: str, build_id: str) -> Optional[Dict[str, Any]]:
        """Get build metadata from started.json file.
        
        Args:
            job_name: The name of the job
            build_id: The build ID
            
        Returns:
            Metadata dictionary or None if not found
        """
        metadata_url = f"{GCS_URL}/logs/{job_name}/{build_id}/started.json"
        
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(metadata_url)
                if response.status_code == 200:
                    return response.json()
        except Exception:
            pass
        
        return None
    
    @staticmethod
    async def find_pr_builds_in_regular_logs(job_name: str, pr_number: str, max_builds: int = 10) -> List[str]:
        """Find builds for a PR by scanning regular logs for PR metadata.
        
        Args:
            job_name: The name of the job
            pr_number: The PR number to search for
            max_builds: Maximum number of recent builds to check
            
        Returns:
            List of build IDs that are associated with the PR
        """
        all_builds = await GCSService.get_builds_for_job(job_name)
        pr_builds = []
        
        # Check recent builds for PR metadata
        recent_builds = all_builds[:max_builds]
        
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            for build_id in recent_builds:
                try:
                    metadata = await GCSService.get_build_metadata(job_name, build_id)
                    if metadata:
                        # Look for PR number in the metadata
                        refs = metadata.get("refs", {})
                        pulls = refs.get("pulls", [])
                        
                        for pull in pulls:
                            if str(pull.get("number", "")) == pr_number:
                                pr_builds.append(build_id)
                                break
                except Exception:
                    continue
        
        return pr_builds
    
    @staticmethod
    async def get_log_files_in_directory(artifacts_url: str) -> List[str]:
        """Get list of log files in an artifacts directory.
        
        Args:
            artifacts_url: URL to the artifacts directory
            
        Returns:
            List of log file names found in the directory
        """
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(artifacts_url)
                if response.status_code == 200:
                    html_content = response.text
                    
                    # Look for log files in the HTML directory listing
                    log_file_pattern = r'href="([^"]*\.(?:txt|log)[^"]*)"'
                    return re.findall(log_file_pattern, html_content)
        except Exception:
            pass
        
        return []
    
    @staticmethod
    async def download_file_content(url: str) -> Optional[str]:
        """Download content from a URL.
        
        Args:
            url: The URL to download from
            
        Returns:
            File content as string or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(url)
                
                # Check if we got HTML (directory listing) instead of actual content
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type and '<!doctype html>' in response.text:
                    return None
                
                if response.status_code == 200:
                    content = response.text
                    # Basic check to see if this looks like actual file content
                    if content and not content.strip().startswith('<!doctype html>'):
                        return content
        except Exception:
            pass
        
        return None 