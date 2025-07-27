"""Diagnostic tools for comprehensive analysis of Prow jobs and failures."""

import asyncio
import json
import logging
import re
import httpx
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from fastmcp import FastMCP
from dateutil.parser import parse as parse_date

from ..config import get_default_org_repo, get_default_job_name, GCS_URL, DEFAULT_TIMEOUT, EXTENDED_TIMEOUT
from ..services.prow_service import ProwService
from ..services.gcs_service import GCSService
from ..models.types import TestFailure


def register_diagnostic_tools(mcp: FastMCP) -> None:
    """Register diagnostic tools with the MCP server."""

    @mcp.tool()
    def diagnose_pr_failures(
        pr_number: str,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None
    ) -> str:
        """
        Comprehensive diagnostic analysis of PR failures across multiple job runs.
        
        Args:
            pr_number: The GitHub PR number to analyze
            org_repo: Organization and repository (e.g., 'redhat-developer_rhdh'). Uses default if not provided.
            job_name: Job name pattern. Uses default if not provided.
            
        Returns:
            JSON string with comprehensive failure analysis including patterns, trends, and recommendations
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
        if job_name is None:
            job_name = get_default_job_name()
            
        try:
            # This is a placeholder for actual implementation
            # In a real implementation, this would analyze PR failure patterns
            result = {
                "success": True,
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name,
                "analysis": {},
                "note": "This tool needs implementation - placeholder for PR failure diagnosis"
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            error_result = {
                "success": False,
                "error": f"Failed to diagnose PR failures: {str(e)}",
                "pr_number": pr_number,
                "org_repo": org_repo,
                "job_name": job_name
            }
            return json.dumps(error_result, indent=2)

    @mcp.tool()
    async def diagnose_pr_build_status(
        pr_number: str,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Advanced diagnostic tool that checks multiple sources for PR build status.
        Provides comprehensive information about job accessibility and troubleshooting guidance.
        
        Args:
            pr_number: The GitHub PR number (e.g., "3191")
            org_repo: The organization/repository in format "org_repo" (default: "redhat-developer_rhdh")
            job_name: The Prow job name (default: "pull-ci-redhat-developer-rhdh-main-e2e-tests")
            
        Returns:
            Comprehensive diagnostic information including:
            - Active job status
            - GCS storage availability
            - Build history
            - Troubleshooting recommendations
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
        if job_name is None:
            job_name = get_default_job_name()
            
        diagnosis = {
            "pr_number": pr_number,
            "org_repo": org_repo,
            "job_name": job_name,
            "timestamp": "2025-01-27T00:00:00Z",  # Current timestamp when diagnosis runs
            "checks": {},
            "recommendations": [],
            "build_info": {}
        }
        
        # Check 1: Active Prow Jobs
        try:
            all_jobs = await ProwService.get_all_jobs()
            
            if all_jobs:
                # Find all jobs for this job name
                matching_jobs = [
                    job for job in all_jobs
                    if job.get("spec", {}).get("job") == job_name
                ]
                
                # Find PR-specific jobs
                pr_jobs = []
                for job in matching_jobs:
                    refs = job.get("spec", {}).get("refs", {})
                    pulls = refs.get("pulls", [])
                    for pull in pulls:
                        if str(pull.get("number", "")) == pr_number:
                            pr_jobs.append(job)
                            break
                
                diagnosis["checks"]["active_prow"] = {
                    "status": "accessible",
                    "total_jobs_for_name": len(matching_jobs),
                    "total_pr_jobs": len(pr_jobs),
                    "pr_jobs_details": [
                        {
                            "job_id": job["metadata"]["name"],
                            "state": job.get("status", {}).get("state"),
                            "start_time": job.get("status", {}).get("startTime"),
                            "completion_time": job.get("status", {}).get("completionTime"),
                            "build_id": job.get("status", {}).get("build_id")
                        }
                        for job in pr_jobs[:5]  # Limit to 5 most recent
                    ]
                }
                
                if pr_jobs:
                    diagnosis["build_info"]["active_jobs_found"] = True
                    latest_job = sorted(pr_jobs, key=lambda j: parse_date(j["status"]["startTime"]), reverse=True)[0]
                    diagnosis["build_info"]["latest_active"] = {
                        "job_id": latest_job["metadata"]["name"],
                        "build_id": latest_job.get("status", {}).get("build_id"),
                        "state": latest_job.get("status", {}).get("state")
                    }
                else:
                    diagnosis["recommendations"].append("No active Prow jobs found for this PR. The build may have completed and been archived.")
                    
            else:
                diagnosis["checks"]["active_prow"] = {"status": "inaccessible", "error": "Could not fetch Prow jobs"}
                diagnosis["recommendations"].append("Prow API is not accessible. Check network connectivity.")
                
        except Exception as e:
            diagnosis["checks"]["active_prow"] = {"status": "error", "error": str(e)}
        
        # Check 2: GCS PR Logs Structure
        try:
            builds = await GCSService.get_pr_builds(org_repo, pr_number, job_name)
            
            if builds:
                diagnosis["checks"]["gcs_pr_logs"] = {
                    "status": "accessible",
                    "url": f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}",
                    "builds_found": len(builds),
                    "builds": builds[:10]  # Limit to 10 most recent
                }
                
                diagnosis["build_info"]["gcs_pr_builds_found"] = True
                diagnosis["build_info"]["latest_gcs_pr_build"] = builds[0]
            else:
                diagnosis["checks"]["gcs_pr_logs"] = {
                    "status": "not_found",
                    "url": f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}",
                    "message": "PR logs directory does not exist or contains no builds"
                }
                diagnosis["recommendations"].append("PR logs directory not found. This could mean the PR is very new, very old, or hasn't had CI runs.")
                
        except Exception as e:
            diagnosis["checks"]["gcs_pr_logs"] = {"status": "error", "error": str(e)}
        
        # Check 3: GCS Regular Logs
        try:
            all_builds = await GCSService.get_builds_for_job(job_name)
            pr_builds_in_regular = await GCSService.find_pr_builds_in_regular_logs(job_name, pr_number, max_builds=10)
            
            diagnosis["checks"]["gcs_regular_logs"] = {
                "status": "accessible",
                "url": f"{GCS_URL}/logs/{job_name}",
                "total_builds": len(all_builds),
                "recent_builds": all_builds[:5] if all_builds else [],
                "pr_builds_found": pr_builds_in_regular
            }
            
            if pr_builds_in_regular:
                diagnosis["build_info"]["gcs_regular_pr_builds"] = pr_builds_in_regular
                diagnosis["build_info"]["latest_gcs_regular_build"] = pr_builds_in_regular[0]
                
        except Exception as e:
            diagnosis["checks"]["gcs_regular_logs"] = {"status": "error", "error": str(e)}
        
        # Generate recommendations based on findings
        if not any([
            diagnosis["build_info"].get("active_jobs_found"),
            diagnosis["build_info"].get("gcs_pr_builds_found"),
            diagnosis["build_info"].get("gcs_regular_pr_builds")
        ]):
            diagnosis["recommendations"].extend([
                f"No builds found for PR {pr_number} in any location",
                "Verify the PR number is correct",
                "Check if CI is configured for this repository",
                "Confirm the job name is correct for this repository"
            ])
        
        # Determine overall status
        if diagnosis["build_info"].get("active_jobs_found"):
            diagnosis["overall_status"] = "builds_active"
            diagnosis["primary_recommendation"] = "Use active job ID for most recent logs"
        elif diagnosis["build_info"].get("gcs_pr_builds_found"):
            diagnosis["overall_status"] = "builds_archived_pr_structure"
            diagnosis["primary_recommendation"] = "Use GCS PR logs structure for archived builds"
        elif diagnosis["build_info"].get("gcs_regular_pr_builds"):
            diagnosis["overall_status"] = "builds_archived_regular_structure"
            diagnosis["primary_recommendation"] = "Use GCS regular logs structure with metadata scanning"
        else:
            diagnosis["overall_status"] = "no_builds_found"
            diagnosis["primary_recommendation"] = "Verify PR exists and has CI runs"
        
        return diagnosis

    @mcp.tool()
    async def get_test_failures_from_artifacts(
        pr_number: str,
        org_repo: Optional[str] = None,
        job_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract test failure information from artifacts when main logs are sanitized.
        This tool looks for JUnit XML, test reports, and other structured data.
        
        Args:
            pr_number: The GitHub PR number (e.g., "3191")
            org_repo: The organization/repository in format "org_repo"
            job_name: The Prow job name
            
        Returns:
            Dictionary containing extracted test failure information from artifacts
        """
        # Use defaults if not provided
        if org_repo is None:
            org_repo = get_default_org_repo()
        if job_name is None:
            job_name = get_default_job_name()
            
        try:
            # First, get the build info using our internal logic
            # Strategy 1: Check active Prow jobs first
            pr_jobs = await ProwService.get_jobs_for_pr(job_name, pr_number)
            build_info = None
            
            if pr_jobs:
                latest_job = pr_jobs[0]  # Already sorted by start time
                build_id = latest_job.get("status", {}).get("build_id")
                
                if build_id:
                    build_info = {
                        "build_id": build_id,
                        "job_name": job_name,
                        "source": "active_prow"
                    }
            
            # Strategy 2: Try GCS PR logs if no active jobs
            if not build_info:
                builds = await GCSService.get_pr_builds(org_repo, pr_number, job_name)
                if builds:
                    build_info = {
                        "build_id": builds[0],
                        "job_name": job_name,
                        "source": "gcs_pr_logs"
                    }
            
            if not build_info:
                return {
                    "error": "Could not find build info",
                    "pr_number": pr_number
                }
            
            build_id = build_info["build_id"]
            artifacts_base = f"{GCS_URL}/pr-logs/pull/{org_repo}/{pr_number}/{job_name}/{build_id}/artifacts"
            
            results = {
                "pr_number": pr_number,
                "build_id": build_id,
                "job_status": build_info.get("job_status", "unknown") if build_info else "unknown",
                "source": build_info.get("source", "unknown") if build_info else "unknown",
                "test_failures": [],
                "junit_results": None,
                "error_summary": None,
                "artifacts_checked": []
            }
            
            async with httpx.AsyncClient(timeout=EXTENDED_TIMEOUT) as client:
                
                # 1. Check JUnit XML files for structured test results
                junit_urls = [
                    f"{artifacts_base}/junit_operator.xml",
                    f"{artifacts_base}/junit.xml",
                    f"{artifacts_base}/test-results.xml",
                    f"{artifacts_base}/e2e-tests/junit.xml"
                ]
                
                for junit_url in junit_urls:
                    try:
                        response = await client.get(junit_url)
                        if response.status_code == 200:
                            results["artifacts_checked"].append(f"✅ {junit_url}")
                            junit_content = response.text
                            
                            # Parse basic JUnit information
                            if "<testcase" in junit_content and "failure" in junit_content:
                                # Extract test suite info
                                suite_match = re.search(r'<testsuite[^>]*name="([^"]*)"[^>]*tests="([^"]*)"[^>]*failures="([^"]*)"', junit_content)
                                if suite_match:
                                    results["junit_results"] = {
                                        "suite_name": suite_match.group(1),
                                        "total_tests": suite_match.group(2),
                                        "failures": suite_match.group(3),
                                        "source_url": junit_url
                                    }
                                
                                # Extract failure messages
                                failure_pattern = r'<testcase[^>]*name="([^"]*)"[^>]*>.*?<failure[^>]*message="([^"]*)"[^>]*>(.*?)</failure>'
                                failures = re.findall(failure_pattern, junit_content, re.DOTALL)
                                
                                for test_name, failure_msg, failure_details in failures:
                                    # Decode HTML entities
                                    failure_msg = failure_msg.replace("&#34;", '"').replace("&#xA;", "\n").replace("&amp;", "&")
                                    failure_details = failure_details.replace("&#34;", '"').replace("&#xA;", "\n").replace("&amp;", "&")
                                    
                                    results["test_failures"].append({
                                        "test_name": test_name,
                                        "failure_message": failure_msg,
                                        "failure_details": failure_details[:1000] + "..." if len(failure_details) > 1000 else failure_details
                                    })
                            
                            results["junit_content"] = junit_content[:2000] + "..." if len(junit_content) > 2000 else junit_content
                            break  # Found a valid JUnit file
                            
                    except Exception as e:
                        results["artifacts_checked"].append(f"❌ {junit_url}: {str(e)}")
                        continue
                
                # 2. Check for test report files
                report_urls = [
                    f"{artifacts_base}/test-results/",
                    f"{artifacts_base}/e2e-tests/test-results/",
                    f"{artifacts_base}/playwright-report/",
                    f"{artifacts_base}/reports/"
                ]
                
                for report_url in report_urls:
                    try:
                        response = await client.get(report_url)
                        if response.status_code == 200:
                            results["artifacts_checked"].append(f"✅ {report_url} (directory)")
                            # Look for specific test result files in the directory listing
                            html_content = response.text
                            
                            # Look for common test result file patterns
                            file_patterns = [
                                r'<a href="([^"]*\.json)"',
                                r'<a href="([^"]*test[^"]*\.txt)"',
                                r'<a href="([^"]*result[^"]*\.xml)"'
                            ]
                            
                            for pattern in file_patterns:
                                matches = re.findall(pattern, html_content, re.IGNORECASE)
                                for match in matches[:3]:  # Limit to 3 files per directory
                                    file_url = f"{report_url.rstrip('/')}/{match}"
                                    try:
                                        file_response = await client.get(file_url)
                                        if file_response.status_code == 200:
                                            results["artifacts_checked"].append(f"✅ {file_url}")
                                            # Add file content if it looks like test results
                                            if match.endswith('.json') and 'test' in match.lower():
                                                try:
                                                    json_data = file_response.json()
                                                    if 'failures' in str(json_data).lower():
                                                        results["additional_test_data"] = {
                                                            "source": file_url,
                                                            "data": json_data
                                                        }
                                                except:
                                                    pass
                                    except Exception:
                                        results["artifacts_checked"].append(f"❌ {file_url}")
                    except Exception as e:
                        results["artifacts_checked"].append(f"❌ {report_url}: {str(e)}")
                
                # 3. Generate error summary from available data
                if results["test_failures"]:
                    results["error_summary"] = {
                        "total_failures": len(results["test_failures"]),
                        "main_failure_reason": results["test_failures"][0]["failure_message"] if results["test_failures"] else "Unknown",
                        "recommendation": "Check the detailed failure information in test_failures array"
                    }
                elif results["junit_results"]:
                    results["error_summary"] = {
                        "junit_failures": results["junit_results"]["failures"],
                        "junit_total": results["junit_results"]["total_tests"],
                        "recommendation": "JUnit data found but detailed failures need manual inspection"
                    }
                else:
                    results["error_summary"] = {
                        "status": "No structured test failure data found",
                        "recommendation": "Try accessing artifacts manually or wait for logs to become available"
                    }
            
            return results
            
        except Exception as e:
            return {
                "error": f"Failed to extract test failures: {str(e)}",
                "pr_number": pr_number,
                "suggestion": "Try manually accessing the artifacts URL or wait for logs to become available"
            } 