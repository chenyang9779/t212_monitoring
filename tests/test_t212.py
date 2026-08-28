import pytest

from app.t212 import Trading212Error, _pagination_params


def test_pagination_params_accepts_expected_relative_path():
    params = _pagination_params(
        "/equity/history/orders?cursor=abc&limit=50",
        "/equity/history/orders",
    )
    assert params == {"cursor": "abc", "limit": "50"}


def test_pagination_params_accepts_api_v0_prefix():
    params = _pagination_params(
        "/api/v0/equity/history/transactions?cursor=xyz",
        "/equity/history/transactions",
    )
    assert params == {"cursor": "xyz"}


def test_pagination_params_rejects_wrong_endpoint():
    with pytest.raises(Trading212Error):
        _pagination_params(
            "/equity/orders?cursor=abc",
            "/equity/history/orders",
        )


def test_pagination_params_rejects_absolute_url():
    with pytest.raises(Trading212Error):
        _pagination_params(
            "https://example.com/equity/history/orders?cursor=abc",
            "/equity/history/orders",
        )
