"""Type definitions and data models for the MCP server."""

from typing import Any, Dict, List, Optional, Tuple, TypedDict
from dataclasses import dataclass


class JobSpec(TypedDict, total=False):
    """Type definition for Prow job specification."""
    job: str
    refs: Dict[str, Any]


class JobStatus(TypedDict, total=False):
    """Type definition for Prow job status."""
    state: str
    startTime: str
    completionTime: str
    url: str
    build_id: str


class ProwJob(TypedDict, total=False):
    """Type definition for a complete Prow job."""
    metadata: Dict[str, Any]
    spec: JobSpec
    status: JobStatus


class PRInfo(TypedDict, total=False):
    """Type definition for PR information."""
    is_pr_job: bool
    org_repo: Optional[str]
    pr_number: Optional[str]


@dataclass
class BuildInfo:
    """Data class for build information."""
    build_id: str
    job_name: str
    pr_number: Optional[str] = None
    org_repo: Optional[str] = None
    build_url: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[str] = None
    total_builds_found: Optional[int] = None


@dataclass
class LogResult:
    """Data class for log retrieval results."""
    build_id: str
    job_name: str
    logs: Optional[str] = None
    artifacts_url: Optional[str] = None
    log_url_used: Optional[str] = None
    error: Optional[str] = None


@dataclass
class TestFailure:
    """Data class for test failure information."""
    test_name: str
    failure_message: str
    failure_details: str


class DiagnosticResult(TypedDict, total=False):
    """Type definition for diagnostic results."""
    pr_number: str
    org_repo: str
    job_name: str
    timestamp: str
    checks: Dict[str, Any]
    recommendations: List[str]
    build_info: Dict[str, Any]
    overall_status: str
    primary_recommendation: str 