"""
Backend tests for ANAF Status Monitor.
Covers:
  - Property 1: HTTP status code classification (tasks 3.3)
  - Unit tests for exception-based classification (task 3.4)
  - Smoke tests for Flask routes and infrastructure (task 5.3)
  - Unit tests for static template structure (task 6.2)
  - Unit tests for auto-refresh behavior (task 8.2)

Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.5, 2.6, 4.1, 4.2, 4.3, 4.5, 5.3
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests
from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the project root is on the path so we can import from api.index
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.index import check_endpoint, EndpointResult, HTML_TEMPLATE  # noqa: E402

# Project root for infrastructure file checks
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

# ---------------------------------------------------------------------------
# Shared test fixture: a minimal endpoint dict
# ---------------------------------------------------------------------------
TEST_ENDPOINT = {"id": "test", "name": "Test", "url": "http://example.com"}


# ---------------------------------------------------------------------------
# Property 1: HTTP status code classification
# Validates: Requirements 1.3, 1.6
# ---------------------------------------------------------------------------

@given(st.integers(min_value=100, max_value=499).filter(lambda c: c != 404))
@settings(max_examples=100)
def test_online_range(status_code):
    """
    For any HTTP status code in [100, 499] except 404, check_endpoint must
    classify the endpoint as Online with the correct code and reason=None.
    """
    mock_response = MagicMock()
    mock_response.status_code = status_code

    with patch("requests.get", return_value=mock_response):
        result = check_endpoint(TEST_ENDPOINT)

    assert result.status == "Online", (
        f"Expected 'Online' for status_code={status_code}, got '{result.status}'"
    )
    assert result.code == status_code, (
        f"Expected code={status_code}, got {result.code}"
    )
    assert result.reason is None, (
        f"Expected reason=None for Online endpoint, got '{result.reason}'"
    )


@given(st.integers(min_value=500))
@settings(max_examples=100)
def test_offline_range_5xx(status_code):
    """
    For any HTTP status code >= 500, check_endpoint must classify the endpoint
    as Offline with reason equal to str(code).
    """
    mock_response = MagicMock()
    mock_response.status_code = status_code

    with patch("requests.get", return_value=mock_response):
        result = check_endpoint(TEST_ENDPOINT)

    assert result.status == "Offline", (
        f"Expected 'Offline' for status_code={status_code}, got '{result.status}'"
    )
    assert result.code == status_code, (
        f"Expected code={status_code}, got {result.code}"
    )
    assert result.reason == str(status_code), (
        f"Expected reason='{status_code}', got '{result.reason}'"
    )


def test_404_maps_to_offline():
    """
    HTTP 404 must be classified as Offline with reason='404'.
    """
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("requests.get", return_value=mock_response):
        result = check_endpoint(TEST_ENDPOINT)

    assert result.status == "Offline"
    assert result.code == 404
    assert result.reason == "404"


# ---------------------------------------------------------------------------
# Unit tests for exception-based classification (task 3.4)
# Validates: Requirements 1.2, 1.4, 1.5, 4.5
# ---------------------------------------------------------------------------

def test_timeout_exception_maps_to_offline():
    """
    Validates: Requirements 1.4
    A requests.Timeout must produce status='Offline', reason='Timeout', code=None.
    """
    with patch("requests.get", side_effect=requests.Timeout):
        result = check_endpoint(TEST_ENDPOINT)

    assert result.status == "Offline"
    assert result.reason == "Timeout"
    assert result.code is None


def test_connection_error_maps_to_offline():
    """
    Validates: Requirements 1.5
    A requests.ConnectionError must produce status='Offline',
    reason='Connection Error', code=None.
    """
    with patch("requests.get", side_effect=requests.ConnectionError):
        result = check_endpoint(TEST_ENDPOINT)

    assert result.status == "Offline"
    assert result.reason == "Connection Error"
    assert result.code is None


def test_get_request_uses_2s_timeout():
    """
    Validates: Requirements 1.2, 4.5
    check_endpoint must call requests.get with timeout=2.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("requests.get", return_value=mock_response) as mock_get:
        check_endpoint(TEST_ENDPOINT)

    mock_get.assert_called_once_with("http://example.com", timeout=2)


# ---------------------------------------------------------------------------
# Smoke tests for Flask routes and infrastructure (task 5.3)
# Validates: Requirements 4.1, 4.2, 4.3
# ---------------------------------------------------------------------------

def test_api_index_file_structure():
    """
    Validates: Requirements 4.1
    api/index.py must exist and contain the Flask app and HTML_TEMPLATE constant.
    """
    api_index_path = os.path.join(PROJECT_ROOT, "api", "index.py")
    assert os.path.isfile(api_index_path), "api/index.py does not exist"

    with open(api_index_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "app = Flask" in content, "api/index.py must contain 'app = Flask'"
    assert "HTML_TEMPLATE" in content, "api/index.py must contain 'HTML_TEMPLATE'"


def test_requirements_txt_contains_dependencies():
    """
    Validates: Requirements 4.2
    requirements.txt must declare flask and requests as dependencies.
    """
    req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    assert os.path.isfile(req_path), "requirements.txt does not exist"

    with open(req_path, "r", encoding="utf-8") as f:
        content = f.read().lower()

    assert "flask" in content, "requirements.txt must contain 'flask'"
    assert "requests" in content, "requirements.txt must contain 'requests'"


def test_vercel_json_routes():
    """
    Validates: Requirements 4.3
    vercel.json must exist and contain a catch-all route pointing to api/index.
    """
    vercel_path = os.path.join(PROJECT_ROOT, "vercel.json")
    assert os.path.isfile(vercel_path), "vercel.json does not exist"

    with open(vercel_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Accept either "rewrites" or "routes" key with a destination of /api/index
    routes_entries = config.get("rewrites", []) + config.get("routes", [])
    assert routes_entries, "vercel.json must contain at least one rewrite/route entry"

    destinations = [
        entry.get("destination", entry.get("dest", ""))
        for entry in routes_entries
    ]
    assert any("api/index" in dest for dest in destinations), (
        f"vercel.json must have a route pointing to api/index; found: {destinations}"
    )


# ---------------------------------------------------------------------------
# Unit tests for static template structure (task 6.2)
# Validates: Requirements 2.1, 2.5, 5.3
# ---------------------------------------------------------------------------

def test_dark_background_in_template():
    """
    Validates: Requirements 2.1
    HTML_TEMPLATE must contain the dark background color #121212.
    """
    assert "#121212" in HTML_TEMPLATE, (
        "HTML_TEMPLATE must contain '#121212' for the dark background color"
    )


def test_html_response_contains_timestamp_element():
    """
    Validates: Requirements 2.5
    HTML_TEMPLATE must contain an element with id="timestamp".
    """
    assert 'id="timestamp"' in HTML_TEMPLATE, (
        "HTML_TEMPLATE must contain an element with id=\"timestamp\""
    )


def test_no_external_cdn_references():
    """
    Validates: Requirements 5.3
    HTML_TEMPLATE must not reference external CDN scripts or stylesheets.
    """
    import re

    # Check for external <script src="..."> — only flag those with http/https or //
    external_scripts = re.findall(r'<script[^>]+src=["\'](?:https?:)?//', HTML_TEMPLATE, re.IGNORECASE)
    assert not external_scripts, (
        f"HTML_TEMPLATE must not contain external <script src=...> references; found: {external_scripts}"
    )

    # Check for external <link href="..."> — only flag those with http/https or //
    external_links = re.findall(r'<link[^>]+href=["\'](?:https?:)?//', HTML_TEMPLATE, re.IGNORECASE)
    assert not external_links, (
        f"HTML_TEMPLATE must not contain external <link href=...> references; found: {external_links}"
    )


# ---------------------------------------------------------------------------
# Unit tests for auto-refresh behavior (task 8.2)
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------

def test_html_auto_refresh_scheduled_at_60s():
    """
    Validates: Requirements 2.6
    HTML_TEMPLATE must schedule the auto-refresh at 60 seconds (60000 ms or 60_000).
    """
    has_60000 = "60000" in HTML_TEMPLATE
    has_60_000 = "60_000" in HTML_TEMPLATE
    assert has_60000 or has_60_000, (
        "HTML_TEMPLATE must contain '60000' or '60_000' to schedule a 60-second auto-refresh"
    )


# ---------------------------------------------------------------------------
# Integration tests for Flask routes (tasks 11.2)
# Validates: Requirements 1.7, 5.2
# ---------------------------------------------------------------------------

from api.index import app, EndpointResult  # noqa: E402 (app already imported above)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_results():
    """Return a minimal list of six-field EndpointResult objects for mocking."""
    return [
        EndpointResult(
            id="xml_validation",
            name="XML Validation",
            url="https://webservicesp.anaf.ro/prod/FCTEL/rest/validare/",
            status="Online",
            code=200,
            reason=None,
        ),
        EndpointResult(
            id="oauth2_token",
            name="OAuth2 Token",
            url="https://logincert.anaf.ro/anaf-oauth2/v1/token",
            status="Offline",
            code=None,
            reason="Timeout",
        ),
        EndpointResult(
            id="efactura_api",
            name="e-Factura API",
            url="https://api.anaf.ro/prod/FCTEL/rest/",
            status="Online",
            code=200,
            reason=None,
        ),
        EndpointResult(
            id="stare_d112",
            name="Stare D112",
            url="https://webservicesp.anaf.ro/prod/StareD112/",
            status="Offline",
            code=503,
            reason="503",
        ),
        EndpointResult(
            id="extra_svc_1",
            name="Extra Service 1",
            url="https://example.com/svc1",
            status="Online",
            code=204,
            reason=None,
        ),
        EndpointResult(
            id="extra_svc_2",
            name="Extra Service 2",
            url="https://example.com/svc2",
            status="Offline",
            code=None,
            reason="Connection Error",
        ),
    ]


def test_api_status_returns_json_array(client):
    """
    Validates: Requirements 1.7
    GET /api/status must return a JSON array where each element contains all
    six required fields (id, name, url, status, code, reason).
    """
    mock_results = _make_results()

    with patch("api.index.check_all_endpoints", return_value=mock_results):
        response = client.get("/api/status")

    assert response.status_code == 200
    assert response.content_type.startswith("application/json"), (
        f"Expected application/json, got {response.content_type}"
    )

    data = response.get_json()
    assert isinstance(data, list), "Response body must be a JSON array"
    assert len(data) == len(mock_results), (
        f"Expected {len(mock_results)} items, got {len(data)}"
    )

    required_fields = {"id", "name", "url", "status", "code", "reason"}
    for item in data:
        missing = required_fields - item.keys()
        assert not missing, f"Item missing fields: {missing} — item: {item}"


def test_index_route_embeds_initial_data(client):
    """
    Validates: Requirements 5.2
    GET / must embed window.__INITIAL_DATA__ as a valid JSON array in the HTML,
    with no escaping issues (| safe filter must be applied in the template).
    """
    mock_results = _make_results()

    with patch("api.index.check_all_endpoints", return_value=mock_results):
        response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "window.__INITIAL_DATA__" in html, (
        "Response HTML must contain 'window.__INITIAL_DATA__'"
    )

    # Extract the JSON array between the assignment and the semicolon
    import re
    match = re.search(r"window\.__INITIAL_DATA__\s*=\s*(\[.*?\]);", html, re.DOTALL)
    assert match, "Could not find a parseable window.__INITIAL_DATA__ = [...]; in the HTML"

    raw_json = match.group(1)
    # Verify no HTML-entity escaping crept in (| safe must have been used)
    assert "&lt;" not in raw_json, "JSON was HTML-escaped — ensure the '| safe' filter is applied"
    assert "&gt;" not in raw_json, "JSON was HTML-escaped — ensure the '| safe' filter is applied"

    parsed = json.loads(raw_json)
    assert isinstance(parsed, list), "Embedded __INITIAL_DATA__ must be a JSON array"
    assert len(parsed) == len(mock_results)

    required_fields = {"id", "name", "url", "status", "code", "reason"}
    for item in parsed:
        missing = required_fields - item.keys()
        assert not missing, f"Embedded item missing fields: {missing} — item: {item}"
