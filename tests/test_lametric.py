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
    """Test SSDP discovery finding device and replacing host in URL"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    # Mock environment with full widget URL
    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock _discover_lametric to return discovered IP
    async def mock_discover(timeout=10.0):
        return "192.168.1.100"

    mocker.patch('sinks.lametric._discover_lametric', mock_discover)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push which should trigger discovery
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made
    mock_to_thread.assert_called_once()

    # Verify URL has discovered IP but original path/secret
    called_url = mock_to_thread.call_args[0][1]
    assert called_url == "http://192.168.1.100:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"


@pytest.mark.asyncio
async def test_discovery_finds_zero_devices(mocker):
    """Test SSDP discovery finding no devices (falls back to configured URL)"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    # Mock environment with full widget URL
    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock _discover_lametric to return None (no devices)
    async def mock_discover(timeout=10.0):
        return None

    mocker.patch('sinks.lametric._discover_lametric', mock_discover)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push which should use original URL
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made with original URL (discovery failed, fallback)
    mock_to_thread.assert_called_once()
    called_url = mock_to_thread.call_args[0][1]
    assert called_url == base_url


@pytest.mark.asyncio
async def test_discovery_finds_multiple_devices(mocker):
    """Test SSDP discovery with new protocol (returns first device found)"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    # Mock environment with full widget URL
    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock _discover_lametric to return first device found
    async def mock_discover(timeout=10.0):
        return "192.168.1.100"

    mocker.patch('sinks.lametric._discover_lametric', mock_discover)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push which should trigger discovery
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made with discovered IP
    mock_to_thread.assert_called_once()
    called_url = mock_to_thread.call_args[0][1]
    assert called_url == "http://192.168.1.100:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"


@pytest.mark.asyncio
async def test_manual_url_with_discovery_replaces_host(mocker):
    """Test that configured URL gets host replaced by SSDP discovery"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    # Mock environment with full widget URL
    base_url = "http://192.168.1.50:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock _discover_lametric to return discovered IP (different from configured)
    async def mock_discover(timeout=10.0):
        return "192.168.1.200"

    mocker.patch('sinks.lametric._discover_lametric', mock_discover)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made with discovered IP but original path
    mock_to_thread.assert_called_once()
    called_url = mock_to_thread.call_args[0][1]
    assert called_url == "http://192.168.1.200:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"


@pytest.mark.asyncio
async def test_rediscovery_on_ip_change(mocker, caplog):
    """Test re-discovery when device IP changes (DHCP lease renewal)"""
    # Reset URL manager and create one with pre-discovered IP
    lametric_module._url_manager = None

    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Track discovery calls
    discover_calls = []

    async def mock_discover(timeout=10.0):
        # First call (initial discovery) returns old IP
        # Second call (re-discovery) returns new IP
        if len(discover_calls) == 0:
            discover_calls.append("initial")
            return "192.168.1.100"
        else:
            discover_calls.append("rediscovery")
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

    # Call push which should trigger initial discovery, then re-discovery
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify two requests were attempted (original + retry)
    assert call_count == 2

    # Verify re-discovery was triggered
    assert len(discover_calls) == 2, "Both initial discovery and re-discovery should have been called"

    # Verify connection failure was logged
    assert "Connection failed" in caplog.text


@pytest.mark.asyncio
async def test_discovery_only_runs_once(mocker):
    """Test that discovery is only attempted once per URL manager lifecycle"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock _discover_lametric to return one device
    async def mock_discover(timeout=10.0):
        return "192.168.1.100"

    mock_discover_fn = mocker.patch('sinks.lametric._discover_lametric', side_effect=mock_discover)
    mock_to_thread = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call push multiple times
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)
    await push_to_lametric(reading)
    await push_to_lametric(reading)

    # Verify discovery only ran once (IP cached after first call)
    assert mock_discover_fn.call_count == 1

    # All three pushes should succeed with cached IP
    assert mock_to_thread.call_count == 3

    # Verify URL manager cached the discovery state
    url_manager = lametric_module._url_manager
    assert url_manager.discovered_ip == "192.168.1.100"
    assert url_manager.discovery_attempted == True


# URL Construction Tests (the SINGLE place where URLs are built)

def test_replace_host_standard_url():
    """Test _replace_host() with standard widget URL"""
    original = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    new_ip = "192.168.2.10"
    result = lametric_module.LaMetricURLManager._replace_host(original, new_ip)
    assert result == "http://192.168.2.10:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"


def test_replace_host_no_port():
    """Test _replace_host() defaults to port 8080 when not specified"""
    original = "http://192.168.2.2/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    new_ip = "10.0.0.5"
    result = lametric_module.LaMetricURLManager._replace_host(original, new_ip)
    assert result == "http://10.0.0.5:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"


def test_replace_host_custom_port():
    """Test _replace_host() preserves custom ports"""
    original = "http://192.168.2.2:9999/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    new_ip = "172.16.0.1"
    result = lametric_module.LaMetricURLManager._replace_host(original, new_ip)
    assert result == "http://172.16.0.1:9999/api/v2/widget/update/com.lametric.diy.devwidget/secret123"


def test_replace_host_with_query_params():
    """Test _replace_host() preserves query parameters"""
    original = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123?param=value"
    new_ip = "192.168.2.7"
    result = lametric_module.LaMetricURLManager._replace_host(original, new_ip)
    assert result == "http://192.168.2.7:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123?param=value"


def test_replace_host_preserves_scheme():
    """Test _replace_host() preserves HTTPS scheme"""
    original = "https://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    new_ip = "192.168.2.7"
    result = lametric_module.LaMetricURLManager._replace_host(original, new_ip)
    assert result == "https://192.168.2.7:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"


def test_replace_host_long_secret():
    """Test _replace_host() preserves long widget secrets"""
    original = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/f3b7537fe7a3460db469a9722af3e6a8"
    new_ip = "192.168.2.7"
    result = lametric_module.LaMetricURLManager._replace_host(original, new_ip)
    assert result == "http://192.168.2.7:8080/api/v2/widget/update/com.lametric.diy.devwidget/f3b7537fe7a3460db469a9722af3e6a8"
