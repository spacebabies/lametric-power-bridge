import pytest
from bridge import push_to_lametric

@pytest.mark.asyncio
async def test_push_to_lametric_import_power(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('bridge.send_http_payload')

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
    mock_send = mocker.patch('bridge.send_http_payload')

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