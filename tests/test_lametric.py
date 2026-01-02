import pytest
import os
from sources.base import PowerReading
from sinks.lametric import push_to_lametric, push_to_lametric_stale
import sinks.lametric as lametric_module

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

@pytest.mark.asyncio
async def test_push_to_lametric_stale(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('sinks.lametric.send_http_payload')

    # Call the stale data function
    await push_to_lametric_stale()

    # Verify the payload for stale data indicator
    expected_payload_stale = {
        "frames": [
            {
                "text": "-- W",
                "icon": 1059,
                "index": 0
            }
        ]
    }
    mock_send.assert_called_with(expected_payload_stale)


# Discovery tests

@pytest.mark.asyncio
async def test_discovery_finds_one_device(mocker):
    """Test SSDP discovery finding exactly one LaMetric device"""
    # Reset discovery state
    lametric_module._discovered_ip = None
    lametric_module._discovery_attempted = False

    # Mock environment (no manual URL configured, but API key present)
    mocker.patch('sinks.lametric.LAMETRIC_URL', None)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock async_search to return one device
    async def mock_search(timeout, search_target):
        yield {"location": "http://192.168.1.100:8080/description.xml"}

    mocker.patch('sinks.lametric.async_search', mock_search)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push which should trigger discovery
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made to discovered IP
    mock_to_thread.assert_called_once()

    # Verify IP was cached
    assert lametric_module._discovered_ip == "192.168.1.100"


@pytest.mark.asyncio
async def test_discovery_finds_zero_devices(mocker, caplog):
    """Test SSDP discovery finding no devices (requires manual config)"""
    # Reset discovery state
    lametric_module._discovered_ip = None
    lametric_module._discovery_attempted = False

    # Mock environment (no manual URL configured, but API key present)
    mocker.patch('sinks.lametric.LAMETRIC_URL', None)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock async_search to return no devices
    async def mock_search(timeout, search_target):
        # Empty generator (no devices found)
        return
        yield  # Unreachable, makes this a generator

    mocker.patch('sinks.lametric.async_search', mock_search)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push which should trigger discovery
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify NO request was made (no device found)
    mock_to_thread.assert_not_called()

    # Verify warning was logged
    assert "No devices found via SSDP discovery" in caplog.text


@pytest.mark.asyncio
async def test_discovery_finds_multiple_devices(mocker, caplog):
    """Test SSDP discovery finding 2+ devices (requires manual config)"""
    # Reset discovery state
    lametric_module._discovered_ip = None
    lametric_module._discovery_attempted = False

    # Mock environment (no manual URL configured, but API key present)
    mocker.patch('sinks.lametric.LAMETRIC_URL', None)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock async_search to return multiple devices
    async def mock_search(timeout, search_target):
        yield {"location": "http://192.168.1.100:8080/description.xml"}
        yield {"location": "http://192.168.1.101:8080/description.xml"}

    mocker.patch('sinks.lametric.async_search', mock_search)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push which should trigger discovery
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify NO request was made (ambiguous discovery)
    mock_to_thread.assert_not_called()

    # Verify warning was logged about multiple devices
    assert "Found 2 devices" in caplog.text
    assert "Set LAMETRIC_URL manually" in caplog.text


@pytest.mark.asyncio
async def test_manual_url_skips_discovery(mocker):
    """Test that manual LAMETRIC_URL configuration skips discovery"""
    # Reset discovery state
    lametric_module._discovered_ip = None
    lametric_module._discovery_attempted = False

    # Mock environment with manual URL and API key
    manual_url = "http://192.168.1.50:8080/api/v2/device/notifications"
    mocker.patch('sinks.lametric.LAMETRIC_URL', manual_url)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock async_search (should NOT be called)
    mock_search = mocker.patch('sinks.lametric.async_search')
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made (via to_thread)
    mock_to_thread.assert_called_once()

    # Verify discovery was NOT called
    mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_rediscovery_on_ip_change(mocker, caplog):
    """Test re-discovery when device IP changes (DHCP lease renewal)"""
    # Set initial discovered IP
    lametric_module._discovered_ip = "192.168.1.100"
    lametric_module._discovery_attempted = True

    # Mock environment (no manual URL, but API key present)
    mocker.patch('sinks.lametric.LAMETRIC_URL', None)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock _discover_lametric to return new IP and track if it was called
    discover_called = False

    async def mock_discover(timeout):
        nonlocal discover_called
        discover_called = True
        return "192.168.1.101"

    mocker.patch('sinks.lametric._discover_lametric', mock_discover)

    # Mock asyncio.to_thread to simulate connection failure then success
    call_count = 0

    async def mock_to_thread(func, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call fails with ConnectionError
            import requests
            raise requests.exceptions.ConnectionError("Connection refused")
        # Second call (after re-discovery) succeeds
        return None

    mocker.patch('sinks.lametric.asyncio.to_thread', mock_to_thread)

    # Call push which should trigger re-discovery
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify two requests were attempted (original + retry)
    assert call_count == 2

    # Verify re-discovery was triggered
    assert discover_called, "Re-discovery should have been called"

    # Verify connection failure was logged
    assert "Connection failed" in caplog.text

    # Verify new IP was cached
    assert lametric_module._discovered_ip == "192.168.1.101"


@pytest.mark.asyncio
async def test_discovery_only_runs_once(mocker):
    """Test that discovery is only attempted once per process lifecycle"""
    # Reset discovery state
    lametric_module._discovered_ip = None
    lametric_module._discovery_attempted = False

    # Mock environment (no manual URL, but API key present)
    mocker.patch('sinks.lametric.LAMETRIC_URL', None)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock async_search to return one device
    async def mock_search(timeout, search_target):
        yield {"location": "http://192.168.1.100:8080/description.xml"}

    mock_async_search = mocker.patch('sinks.lametric.async_search', mock_search)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push multiple times
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)
    await push_to_lametric(reading)
    await push_to_lametric(reading)

    # Verify discovery only ran once (IP cached after first call)
    assert lametric_module._discovery_attempted == True
    assert lametric_module._discovered_ip == "192.168.1.100"

    # All three pushes should succeed with cached IP
    assert mock_to_thread.call_count == 3
