import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
import json
from dateutil.parser import parse as parse_date

# Import the functions we want to test from the refactored modules
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import from refactored modules
from mcp_server.utils.pr_parser import extract_pr_info
from mcp_server.utils.url_builder import construct_log_urls
from mcp_server.services.pr_finder import smart_pr_build_finder
from mcp_server.config import PROW_URL, GCS_URL

# Import tool implementations that need testing
from mcp_server.tools.job_tools import get_latest_job_run_impl
from mcp_server.tools.log_tools import get_build_logs_impl
from mcp_server.services.prow_service import ProwService
from mcp_server.services.gcs_service import GCSService

# For testing the MCP tools, we need to create a server and call tools
from mcp_server.main import create_server

# Helper functions for testing MCP tools
async def call_mcp_tool(tool_name: str, **kwargs):
    """Helper to call MCP tools through the server."""
    server = create_server()
    tools = await server.list_tools()
    tool = next((t for t in tools if t.name == tool_name), None)
    if not tool:
        raise ValueError(f"Tool {tool_name} not found")
    
    # For testing, we'll mock the tool call
    if tool_name == "get_latest_job_run":
        return await get_latest_job_run_impl(kwargs.get("job_name"))
    elif tool_name == "get_build_logs":
        return await get_build_logs_impl(
            kwargs.get("job_name"), 
            kwargs.get("build_id"), 
            kwargs.get("job_spec")
        )
    else:
        raise NotImplementedError(f"Test helper for {tool_name} not implemented")


class TestExtractPrInfo:
    """Test the extract_pr_info function."""
    
    def test_extract_pr_info_from_job_spec_with_pulls(self):
        """Test extracting PR info from job spec with pulls."""
        job_spec = {
            "refs": {
                "pulls": [{"number": 1234}],
                "org": "redhat-developer",
                "repo": "rhdh",
                "base_ref": "main"
            }
        }
        
        is_pr, org_repo, pr_number = extract_pr_info(job_spec)
        
        assert is_pr is True
        assert org_repo == "redhat-developer_rhdh"
        assert pr_number == "1234"
    
    def test_extract_pr_info_from_job_spec_without_pulls(self):
        """Test extracting PR info from job spec without pulls."""
        job_spec = {
            "refs": {
                "org": "redhat-developer",
                "repo": "rhdh",
                "base_ref": "main"
            }
        }
        
        is_pr, org_repo, pr_number = extract_pr_info(job_spec)
        
        assert is_pr is False
        assert org_repo is None
        assert pr_number is None
    
    def test_extract_pr_info_from_job_name_pattern(self):
        """Test extracting PR info from job name pattern."""
        job_name = "pull-ci-redhat-developer-rhdh-main-e2e-tests"
        
        is_pr, org_repo, pr_number = extract_pr_info(None, job_name)
        
        assert is_pr is True
        assert org_repo == "redhat-developer_rhdh"
        assert pr_number is None  # Can't extract PR number from job name
    
    def test_extract_pr_info_from_non_pr_job_name(self):
        """Test extracting PR info from non-PR job name."""
        job_name = "periodic-ci-redhat-developer-rhdh-main-e2e-tests"
        
        is_pr, org_repo, pr_number = extract_pr_info(None, job_name)
        
        assert is_pr is False
        assert org_repo is None
        assert pr_number is None
    
    def test_extract_pr_info_empty_inputs(self):
        """Test extracting PR info with empty inputs."""
        is_pr, org_repo, pr_number = extract_pr_info(None, None)
        
        assert is_pr is False
        assert org_repo is None
        assert pr_number is None
    
    def test_extract_pr_info_malformed_job_spec(self):
        """Test extracting PR info with malformed job spec."""
        job_spec = {"invalid": "data"}
        
        is_pr, org_repo, pr_number = extract_pr_info(job_spec)
        
        assert is_pr is False
        assert org_repo is None
        assert pr_number is None
    
    def test_extract_pr_info_with_multiple_pulls(self):
        """Test extracting PR info when multiple pulls exist (should use first one)."""
        job_spec = {
            "refs": {
                "pulls": [{"number": 1234}, {"number": 5678}],
                "org": "test-org",
                "repo": "test-repo"
            }
        }
        
        is_pr, org_repo, pr_number = extract_pr_info(job_spec)
        
        assert is_pr is True
        assert org_repo == "test-org_test-repo"
        assert pr_number == "1234"  # Should use first pull
    
    def test_extract_pr_info_job_name_edge_cases(self):
        """Test various edge cases for job name parsing."""
        test_cases = [
            ("pull-ci-a-b-main-test", True, "a_b"),
            ("pull-ci-org-repo", False, None),  # Too short
            ("not-a-pull-job", False, None),
            ("pull-ci-org-repo-branch-very-long-test-name-with-dashes", True, "org_repo"),
        ]
        
        for job_name, expected_is_pr, expected_org_repo in test_cases:
            is_pr, org_repo, pr_number = extract_pr_info(None, job_name)
            assert is_pr == expected_is_pr
            assert org_repo == expected_org_repo


class TestConstructLogUrls:
    """Test the construct_log_urls function."""
    
    def test_construct_pr_job_urls_with_pr_number(self):
        """Test constructing URLs for PR job with PR number."""
        job_name = "pull-ci-redhat-developer-rhdh-main-e2e-tests"
        build_id = "1234567890"
        job_spec = {
            "refs": {
                "pulls": [{"number": 5678}],
                "org": "redhat-developer",
                "repo": "rhdh"
            }
        }
        
        artifacts_url, log_urls, pr_info = construct_log_urls(job_name, build_id, job_spec)
        
        expected_base = f"{GCS_URL}/pr-logs/pull/redhat-developer_rhdh/5678/{job_name}/{build_id}"
        assert expected_base in str(log_urls)
        assert "build-log.txt" in str(log_urls)
        assert artifacts_url == f"{expected_base}/artifacts"
    
    def test_construct_regular_job_urls(self):
        """Test constructing URLs for regular job."""
        job_name = "periodic-ci-test-job"
        build_id = "1234567890"
        
        artifacts_url, log_urls, pr_info = construct_log_urls(job_name, build_id)
        
        expected_base = f"{GCS_URL}/logs/{job_name}/{build_id}"
        assert expected_base in str(log_urls)
        assert artifacts_url == f"{expected_base}/artifacts"
    
    def test_construct_urls_with_special_characters(self):
        """Test URL construction with special characters in job names."""
        job_name = "pull-ci-org-repo_with.dots-main-test"
        build_id = "build_123.456"
        
        artifacts_url, log_urls, pr_info = construct_log_urls(job_name, build_id)
        
        # Should handle special characters without breaking
        assert job_name in str(log_urls)
        assert build_id in str(log_urls)


class TestMcpTools:
    """Test the MCP tool functions with proper mocking."""
    
    @pytest.fixture
    def mock_httpx_response(self):
        """Create a mock httpx response."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.status_code = 200
        return mock_response
    
    @pytest.mark.asyncio
    async def test_get_latest_job_run_success(self, mock_httpx_response):
        """Test successful get_latest_job_run."""
        mock_data = {
            "items": [
                {
                    "metadata": {"name": "job-123"},
                    "spec": {"job": "test-job"},
                    "status": {
                        "state": "success",
                        "startTime": "2024-01-01T10:00:00Z",
                        "completionTime": "2024-01-01T10:30:00Z",
                        "url": "https://example.com/job-123"
                    }
                },
                {
                    "metadata": {"name": "job-456"},
                    "spec": {"job": "test-job"},
                    "status": {
                        "state": "failure",
                        "startTime": "2024-01-01T09:00:00Z",
                        "completionTime": "2024-01-01T09:30:00Z",
                        "url": "https://example.com/job-456"
                    }
                }
            ]
        }
        
        mock_httpx_response.json.return_value = mock_data
        
        with patch('httpx.AsyncClient.get', return_value=mock_httpx_response):
            result = await get_latest_job_run("test-job")
        
        assert result["job_id"] == "job-123"
        assert result["state"] == "success"
        assert result["start"] == "2024-01-01T10:00:00Z"
        assert result["completion"] == "2024-01-01T10:30:00Z"
        assert result["url"] == "https://example.com/job-123"
    
    @pytest.mark.asyncio
    async def test_get_latest_job_run_no_matching_jobs(self, mock_httpx_response):
        """Test get_latest_job_run with no matching jobs."""
        mock_data = {"items": []}
        mock_httpx_response.json.return_value = mock_data
        
        with patch('mcp_server.utils.http_client.make_request', return_value=mock_data):
            result = await get_latest_job_run_impl("nonexistent-job")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_latest_job_run_sort_by_time(self, mock_httpx_response):
        """Test that get_latest_job_run correctly sorts by start time."""
        mock_data = {
            "items": [
                {
                    "metadata": {"name": "older-job"},
                    "spec": {"job": "test-job"},
                    "status": {
                        "state": "success",
                        "startTime": "2024-01-01T08:00:00Z",
                    }
                },
                {
                    "metadata": {"name": "newer-job"},
                    "spec": {"job": "test-job"},
                    "status": {
                        "state": "success",
                        "startTime": "2024-01-01T10:00:00Z",
                    }
                }
            ]
        }
        
        mock_httpx_response.json.return_value = mock_data
        
        with patch('httpx.AsyncClient.get', return_value=mock_httpx_response):
            result = await get_latest_job_run("test-job")
        
        # Should return the newer job
        assert result["job_id"] == "newer-job"
    
    @pytest.mark.asyncio
    async def test_get_job_logs_success(self, mock_httpx_response):
        """Test successful get_job_logs."""
        # Mock prowjobs response
        prowjobs_data = {
            "items": [
                {
                    "metadata": {"name": "test-job-id"},
                    "status": {"url": "https://example.com/logs"}
                }
            ]
        }
        
        # Mock log content response
        log_content = "Build started\nRunning tests\nBuild completed successfully"
        
        with patch('httpx.AsyncClient.get') as mock_get:
            # First call returns prowjobs data
            mock_response_1 = Mock()
            mock_response_1.raise_for_status = Mock()
            mock_response_1.json.return_value = prowjobs_data
            
            # Second call returns log content
            mock_response_2 = Mock()
            mock_response_2.raise_for_status = Mock()
            mock_response_2.text = log_content
            mock_response_2.status_code = 200
            
            mock_get.side_effect = [mock_response_1, mock_response_2]
            
            result = await get_job_logs("test-job-id")
        
        assert result["job_id"] == "test-job-id"
        assert result["logs"] == log_content
        assert result["artifacts_url"] is not None
    
    @pytest.mark.asyncio
    async def test_get_build_logs_success(self, mock_httpx_response):
        """Test successful get_build_logs."""
        log_content = "Build log content here"
        mock_httpx_response.text = log_content
        mock_httpx_response.status_code = 200
        
        with patch('httpx.AsyncClient.get', return_value=mock_httpx_response):
            result = await get_build_logs("test-job", "build-123")
        
        assert result["job_name"] == "test-job"
        assert result["build_id"] == "build-123"
        assert result["logs"] == log_content
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_get_build_logs_with_job_spec(self):
        """Test get_build_logs with job specification."""
        job_spec = {
            "refs": {
                "pulls": [{"number": 1234}],
                "org": "test-org",
                "repo": "test-repo"
            }
        }
        
        log_content = "Build log with PR info"
        mock_response = Mock()
        mock_response.text = log_content
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            result = await get_build_logs("test-job", "build-123", job_spec)
        
        assert result["job_name"] == "test-job"
        assert result["build_id"] == "build-123"
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_get_latest_prow_build_for_pr(self, mock_httpx_response):
        """Test get_latest_prow_build_for_pr with mock data."""
        mock_data = {
            "items": [
                {
                    "metadata": {"name": "job-789"},
                    "spec": {
                        "job": "pull-ci-redhat-developer-rhdh-main-e2e-tests",
                        "refs": {
                            "pulls": [{"number": 1234}],
                            "org": "redhat-developer",
                            "repo": "rhdh"
                        }
                    },
                    "status": {
                        "startTime": "2024-01-01T12:00:00Z",
                        "build_id": "987654321"
                    }
                }
            ]
        }
        
        mock_httpx_response.json.return_value = mock_data
        
        with patch('httpx.AsyncClient.get', return_value=mock_httpx_response):
            result = await get_latest_prow_build_for_pr("1234")
        
        assert result["pr_number"] == "1234"
        assert result["build_id"] is not None
        assert result["source"] == "active_prow"
    
    @pytest.mark.asyncio
    async def test_diagnose_pr_build_status_basic(self):
        """Test basic functionality of diagnose_pr_build_status."""
        with patch('httpx.AsyncClient.get') as mock_get:
            # Mock empty response to avoid actual network calls
            mock_response = Mock()
            mock_response.json.return_value = {"items": []}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = await diagnose_pr_build_status("1234")
        
        # Should return diagnostic structure
        assert "pr_number" in result
        assert "checks" in result
        assert "recommendations" in result
        assert result["pr_number"] == "1234"


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """Test handling of network errors."""
        with patch('httpx.AsyncClient.get', side_effect=Exception("Network error")):
            result = await get_latest_job_run("test-job")
            
            # Should return None or error response rather than crash
            assert result is None or "error" in result
    
    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        """Test handling of invalid JSON responses."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            result = await get_latest_job_run("test-job")
            
            # Should handle JSON decode error gracefully
            assert result is None or "error" in result
    
    @pytest.mark.asyncio
    async def test_http_error_handling(self):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 404")
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            result = await get_latest_job_run("test-job")
            
            # Should handle HTTP errors gracefully
            assert result is None or "error" in result
    
    def test_extract_pr_info_exception_handling(self):
        """Test that extract_pr_info handles exceptions gracefully."""
        # Test with object that will cause an exception when accessed
        malformed_spec = Mock()
        malformed_spec.get.side_effect = Exception("Access error")
        
        is_pr, org_repo, pr_number = extract_pr_info(malformed_spec)
        
        assert is_pr is False
        assert org_repo is None
        assert pr_number is None
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test handling of request timeouts."""
        import asyncio
        
        with patch('httpx.AsyncClient.get', side_effect=asyncio.TimeoutError("Request timeout")):
            result = await get_latest_job_run("test-job")
            
            # Should handle timeout gracefully
            assert result is None or "error" in result
    
    @pytest.mark.asyncio
    async def test_empty_log_content(self):
        """Test handling of empty log content."""
        mock_response = Mock()
        mock_response.text = ""
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            result = await get_build_logs("test-job", "build-123")
        
        assert result["logs"] == ""
        assert result["success"] is True


class TestPerformance:
    """Test performance-related scenarios."""
    
    @pytest.mark.asyncio
    async def test_large_job_list_handling(self):
        """Test handling of large job lists."""
        # Create a large mock dataset
        large_job_list = []
        for i in range(1000):
            large_job_list.append({
                "metadata": {"name": f"job-{i}"},
                "spec": {"job": "test-job"},
                "status": {
                    "state": "success",
                    "startTime": f"2024-01-01T{i % 24:02d}:00:00Z",
                }
            })
        
        mock_data = {"items": large_job_list}
        mock_response = Mock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            import time
            start_time = time.time()
            result = await get_latest_job_run("test-job")
            end_time = time.time()
        
        # Should handle large datasets efficiently (under 1 second)
        assert (end_time - start_time) < 1.0
        assert result is not None
        assert result["job_id"] == "job-999"  # Should get the latest one


class TestIntegration:
    """Integration tests that test multiple components together."""
    
    @pytest.mark.asyncio
    async def test_pr_workflow_integration(self):
        """Test the full workflow for getting PR logs."""
        # This would test the integration between multiple functions
        # In a real scenario, you might mock the entire chain
        pass
    
    def test_url_construction_with_various_inputs(self):
        """Test URL construction with various input combinations."""
        test_cases = [
            {
                "job_name": "pull-ci-org-repo-main-test",
                "build_id": "123",
                "job_spec": {"refs": {"pulls": [{"number": 456}], "org": "org", "repo": "repo"}},
                "expected_pattern": "pr-logs/pull/org_repo/456"
            },
            {
                "job_name": "periodic-job",
                "build_id": "789",
                "job_spec": None,
                "expected_pattern": "logs/periodic-job/789"
            }
        ]
        
        for case in test_cases:
            artifacts_url, log_urls, pr_info = construct_log_urls(
                case["job_name"], 
                case["build_id"], 
                case["job_spec"]
            )
            
            # Check that expected pattern appears in the URLs
            url_string = str(log_urls) + str(artifacts_url)
            assert case["expected_pattern"] in url_string
    
    @pytest.mark.asyncio
    async def test_complete_pr_analysis_workflow(self):
        """Test a complete workflow from PR number to test failure analysis."""
        pr_number = "1234"
        
        # Mock the entire chain of calls
        with patch('httpx.AsyncClient.get') as mock_get:
            # Mock responses for different endpoints
            mock_responses = [
                Mock(json=lambda: {"items": []}, raise_for_status=Mock()),  # prowjobs
                Mock(text="No builds found", status_code=404, raise_for_status=Mock()),  # GCS
            ]
            mock_get.side_effect = mock_responses
            
            # Test that we can call multiple functions in sequence without errors
            build_result = await get_latest_prow_build_for_pr(pr_number)
            diagnosis_result = await diagnose_pr_build_status(pr_number)
            
            # Both should complete without errors
            assert build_result is not None
            assert diagnosis_result is not None


class TestDataValidation:
    """Test data validation and input sanitization."""
    
    @pytest.mark.parametrize("pr_number", [
        "123",
        "0001",
        "99999",
        "1234567890"
    ])
    @pytest.mark.asyncio
    async def test_valid_pr_numbers(self, pr_number):
        """Test that various valid PR number formats are accepted."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"items": []}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = await get_latest_prow_build_for_pr(pr_number)
            assert result["pr_number"] == pr_number
    
    @pytest.mark.parametrize("invalid_input", [
        "",
        None,
        "abc",
        "12.34",
        "-123"
    ])
    @pytest.mark.asyncio
    async def test_invalid_pr_numbers(self, invalid_input):
        """Test handling of invalid PR number inputs."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"items": []}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            # Should handle invalid inputs gracefully
            try:
                result = await get_latest_prow_build_for_pr(str(invalid_input) if invalid_input is not None else "")
                # If no exception, result should indicate the input was processed
                assert result is not None
            except (TypeError, ValueError):
                # Some invalid inputs might raise exceptions, which is acceptable
                pass


# Test utilities for running tests
def run_tests():
    """Run all tests and return results."""
    # This can be used if running tests manually
    pytest.main([__file__, "-v"])


def run_specific_test_class(test_class_name):
    """Run tests for a specific test class."""
    pytest.main([f"{__file__}::{test_class_name}", "-v"])


def run_with_coverage():
    """Run tests with coverage reporting."""
    pytest.main([__file__, "--cov=mcp_server", "--cov-report=html", "--cov-report=term", "-v"])


if __name__ == "__main__":
    # Run tests when file is executed directly
    run_tests()


