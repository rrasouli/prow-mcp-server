"""Data models and type definitions for the MCP server."""

# Import types explicitly to avoid import errors
from .types import (
    JobSpec,
    JobStatus, 
    ProwJob,
    PRInfo,
    BuildInfo,
    LogResult,
    TestFailure,
    DiagnosticResult
) 