"""Rate limiting on auth endpoints (slowapi, in-memory storage)."""

from tests.conftest import login


def test_login_rate_limited_after_configured_threshold(client):
    # RATE_LIMIT_LOGIN=5/minute in the test environment.
    statuses = []
    for _ in range(6):
        response = login(client, "ratelimit@example.com", "WhateverPass1")
        statuses.append(response.status_code)
    # The first five attempts pass through (401 for unknown user);
    # the sixth must be rate-limited.
    assert statuses[:5] == [401, 401, 401, 401, 401]
    assert statuses[5] == 429


def test_rate_limit_headers_present_on_429(client):
    """slowapi injects rate-limit headers into its own 429 response. Plain
    HTTPException responses (e.g. 401) intentionally carry none — verified
    empirically against slowapi 0.1.10 behaviour."""
    last = None
    for _ in range(6):
        last = login(client, "headers@example.com", "WhateverPass1")
    assert last is not None and last.status_code == 429
    headers = {k.lower() for k in last.headers.keys()}
    assert "x-ratelimit-limit" in headers
    assert "x-ratelimit-remaining" in headers
    assert "retry-after" in headers
