"""
E2E tests for XHS signature runtime probe.
"""

import pytest

import scripts.check_xhs_signature_runtime as runtime_probe


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSSignatureCanary:
    """E2E smoke tests for signature runtime probe."""

    def test_collect_runtime_probe_shape(self, browser_backend, test_browser_id):
        browser_backend.create_browser(test_browser_id, headless=True)
        try:
            try:
                payload = runtime_probe.collect_runtime_probe(
                    backend=browser_backend,
                    browser_id=test_browser_id,
                    timeout_ms=60000,
                )
            except Exception as exc:
                pytest.skip(f"Unable to probe XHS runtime: {exc}")

            if payload.get("status_code") != 200:
                pytest.skip("Failed to navigate to XHS")

            assert "mnsv2_type" in payload
            assert "mnsv2_source_length" in payload
            assert "global_presence" in payload
            assert "local_storage_presence" in payload
        finally:
            browser_backend.close_browser(test_browser_id)

    def test_evaluate_probe_structure(self, browser_backend, test_browser_id):
        browser_backend.create_browser(test_browser_id, headless=True)
        try:
            try:
                payload = runtime_probe.collect_runtime_probe(
                    backend=browser_backend,
                    browser_id=test_browser_id,
                    timeout_ms=60000,
                )
            except Exception as exc:
                pytest.skip(f"Unable to probe XHS runtime: {exc}")

            if payload.get("status_code") != 200:
                pytest.skip("Failed to navigate to XHS")

            result = runtime_probe.evaluate_probe(payload, {"required_globals": ["mnsv2"]})
            assert "healthy" in result
            assert isinstance(result["checks"], list)
            assert result["checks"]
        finally:
            browser_backend.close_browser(test_browser_id)
