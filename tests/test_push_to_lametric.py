import pytest
from sinks.lametric import push_to_lametric

@pytest.mark.asyncio
async def test_push_to_lametric_import_power(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('sinks.lametric.send_http_payload')

    # Call the function with importing power
    await push_to_lametric(1500)

    # Verify the payload for importing power
    expected_payload_import = {
        "frames": [
            {
                "text": "1500 W",
                "icon": 26337,
                "index": 0
            }
        ]
    }
    mock_send.assert_called_with(expected_payload_import)

@pytest.mark.asyncio
async def test_push_to_lametric_export_power(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('sinks.lametric.send_http_payload')

    # Call the function with exporting power
    await push_to_lametric(-500)

    # Verify the payload for exporting power
    expected_payload_export = {
        "frames": [
            {
                "text": "-500 W",
                "icon": 54077,
                "index": 0
            }
        ]
    }
    mock_send.assert_called_with(expected_payload_export)

@pytest.mark.asyncio
async def test_push_to_lametric_round_float(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('sinks.lametric.send_http_payload')

    # Call the function with exporting power
    await push_to_lametric(180.7)

    # Verify the payload for exporting power
    expected_payload_export = {
        "frames": [
            {
                "text": "181 W",
                "icon": 26337,
                "index": 0
            }
        ]
    }
    mock_send.assert_called_with(expected_payload_export)

@pytest.mark.asyncio
async def test_push_to_lametric_kilowatts(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('sinks.lametric.send_http_payload')

    # Call the function with exporting power
    await push_to_lametric(10500)

    # Verify the payload for exporting power
    expected_payload_export = {
        "frames": [
            {
                "text": "10.5 kW",
                "icon": 26337,
                "index": 0
            }
        ]
    }
    mock_send.assert_called_with(expected_payload_export)

@pytest.mark.asyncio
async def test_push_to_lametric_export_high(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('sinks.lametric.send_http_payload')

    # Call the function with exporting power
    await push_to_lametric(-11000)

    # Verify the payload for exporting power
    expected_payload_export = {
        "frames": [
            {
                "text": "-11.0 kW",
                "icon": 54077,
                "index": 0
            }
        ]
    }
    mock_send.assert_called_with(expected_payload_export)
