from app.exposure import build_exposure, normalize_instrument_metadata


def test_normalize_instrument_metadata_uses_documented_fields():
    item = normalize_instrument_metadata(
        {
            "ticker": "AAPL_US_EQ",
            "isin": "US0378331005",
            "name": "Apple",
            "currencyCode": "USD",
            "type": "STOCK",
            "workingScheduleId": 42,
        }
    )

    assert item is not None
    assert item["ticker"] == "AAPL_US_EQ"
    assert item["isin"] == "US0378331005"
    assert item["currency"] == "USD"
    assert item["type"] == "STOCK"


def test_build_exposure_uses_account_currency_values_without_cross_currency_sum():
    account = {
        "currency": "GBP",
        "investments_current_value": 1000.0,
    }
    positions = [
        {
            "ticker": "AAPL_US_EQ",
            "name": "Apple",
            "currency": "USD",
            "isin": "US0378331005",
            "wallet_current_value": 600.0,
        },
        {
            "ticker": "VUSA_EQ",
            "name": "Vanguard S&P 500",
            "currency": "GBP",
            "isin": "IE00B3XXRP09",
            "wallet_current_value": 400.0,
        },
    ]
    metadata = [
        {
            "ticker": "AAPL_US_EQ",
            "isin": "US0378331005",
            "name": "Apple",
            "currency": "USD",
            "type": "STOCK",
        },
        {
            "ticker": "VUSA_EQ",
            "isin": "IE00B3XXRP09",
            "name": "Vanguard S&P 500",
            "currency": "GBP",
            "type": "ETF",
        },
    ]

    result = build_exposure(account, positions, metadata)

    assert result["account_currency"] == "GBP"
    assert result["metadata_coverage_pct"] == 100.0
    assert result["currency_exposure"] == [
        {"name": "USD", "account_value": 600.0, "weight_pct": 60.0},
        {"name": "GBP", "account_value": 400.0, "weight_pct": 40.0},
    ]
    assert result["type_exposure"] == [
        {"name": "STOCK", "account_value": 600.0, "weight_pct": 60.0},
        {"name": "ETF", "account_value": 400.0, "weight_pct": 40.0},
    ]


def test_build_exposure_marks_missing_metadata_unknown():
    result = build_exposure(
        {"currency": "GBP", "investments_current_value": 100.0},
        [
            {
                "ticker": "UNKNOWN_EQ",
                "name": "Unknown",
                "currency": "EUR",
                "wallet_current_value": 100.0,
            }
        ],
        [],
    )

    assert result["metadata_coverage_pct"] == 0.0
    assert result["type_exposure"][0]["name"] == "UNKNOWN"
    assert result["currency_exposure"][0]["name"] == "EUR"
