import pytest
from sources.base import PowerReading
from sinks.lametric import push_to_lametric

@pytest.mark.asyncio
async def test_push_to_lametric_import_power(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('sinks.lametric.send_http_payload')

    # Call the function with importing power
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

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
    reading = PowerReading(power_watts=-500)
    await push_to_lametric(reading)

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

    # Call the function with a float value that needs rounding
    reading = PowerReading(power_watts=180.7)
    await push_to_lametric(reading)

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

    # Call the function with high power (kW display)
    reading = PowerReading(power_watts=10500)
    await push_to_lametric(reading)

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

    # Call the function with high export power (negative kW)
    reading = PowerReading(power_watts=-11000)
    await push_to_lametric(reading)

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
