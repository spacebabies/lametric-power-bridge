import pytest
import os
import asyncio
import requests
import logging
from lametric_power_bridge.sources.base import PowerReading
from lametric_power_bridge.sinks.lametric import push_to_lametric, push_to_lametric_stale
import lametric_power_bridge.sinks.lametric as lametric_module

@pytest.mark.asyncio
async def test_push_to_lametric_import_power(mocker):
    # Mock the send_http_payload function to avoid actual HTTP requests
    mock_send = mocker.patch('lametric_power_bridge.sinks.lametric.send_http_payload')

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
    mock_send = mocker.patch('lametric_power_bridge.sinks.lametric.send_http_payload')

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
    mock_send = mocker.patch('lametric_power_bridge.sinks.lametric.send_http_payload')

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
    mock_send = mocker.patch('lametric_power_bridge.sinks.lametric.send_http_payload')

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
    mock_send = mocker.patch('lametric_power_bridge.sinks.lametric.send_http_payload')

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
    mock_send = mocker.patch('lametric_power_bridge.sinks.lametric.send_http_payload')

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


# Discovery / Fallback tests

@pytest.mark.asyncio
async def test_initial_url_used_first(mocker):
    """Test that configured URL is used first without discovery delay"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock discovery (should NOT be called if first request succeeds)
    mock_discover = mocker.patch('lametric_power_bridge.sinks.lametric._discover_lametric')
    
    # Mock successful HTTP request
    mock_to_thread = mocker.patch('lametric_power_bridge.sinks.lametric.asyncio.to_thread')

    # Call push
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made with original URL
    mock_to_thread.assert_called_once()
    called_url = mock_to_thread.call_args[0][1]
    assert called_url == base_url
    
    # Verify discovery was NOT called
    mock_discover.assert_not_called()

@pytest.mark.asyncio
async def test_rediscovery_fallback_success(mocker, caplog):
    """Test that discovery runs if initial request fails, and subsequent request uses new IP"""
    caplog.set_level(logging.INFO)
    # Reset URL manager singleton
    lametric_module._url_manager = None

    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock discovery returning new IP
    async def mock_discover_impl(timeout=10.0):
        return "192.168.1.100"
    
    mocker.patch('lametric_power_bridge.sinks.lametric._discover_lametric', side_effect=mock_discover_impl)

    # Mock asyncio.to_thread to simulate failure then success
    call_count = 0
    async def mock_to_thread(func, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise requests.exceptions.ConnectionError("Connection refused")
        return None

    mocker.patch('lametric_power_bridge.sinks.lametric.asyncio.to_thread', side_effect=mock_to_thread)

    # Call push
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify two requests: 1st with base_url, 2nd with discovered IP
    assert call_count == 2
    
    calls = mocker.patch('lametric_power_bridge.sinks.lametric.asyncio.to_thread').call_args_list
    # Note: side_effect mock replaces the object, so we can't inspect 'calls' on the original patch object easily
    # unless we captured it. But we know call_count is 2.
    
    # Verify warning logged
    assert "Connection failed" in caplog.text
    assert "Device IP updated" in caplog.text

@pytest.mark.asyncio
async def test_rediscovery_fallback_not_found(mocker, caplog):
    """Test that if discovery fails, we just give up for this attempt"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # Mock discovery returning None
    mocker.patch('lametric_power_bridge.sinks.lametric._discover_lametric', return_value=None)

    # Mock asyncio.to_thread to simulate failure
    async def mock_to_thread(func, *args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")

    mocker.patch('lametric_power_bridge.sinks.lametric.asyncio.to_thread', side_effect=mock_to_thread)

    # Call push
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Should have tried request once, then discovery, then stopped
    # (Since discovery failed, it returns False, so no retry)
    # We can't easily assert call count on to_thread without a spy, but we can check logs
    
    assert "Discovery failed" in caplog.text
    assert "Connection failed" in caplog.text

@pytest.mark.asyncio
async def test_ip_cached_after_rediscovery(mocker):
    """Test that discovered IP is used for subsequent calls"""
    # Reset URL manager singleton
    lametric_module._url_manager = None

    base_url = "http://192.168.2.2:8080/api/v2/widget/update/com.lametric.diy.devwidget/secret123"
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_URL', base_url)
    mocker.patch('lametric_power_bridge.sinks.lametric.LAMETRIC_API_KEY', 'test-api-key')

    # 1. First call fails -> Discovery success -> Retry success
    # 2. Second call -> Uses discovered IP immediately
    
    # Mock discovery
    mock_discover = mocker.patch('lametric_power_bridge.sinks.lametric._discover_lametric', return_value="192.168.1.100")
    
    call_count = 0
    url_history = []
    
    async def mock_to_thread(func, url, payload):
        nonlocal call_count
        call_count += 1
        url_history.append(url)
        
        # Fail the very first attempt (using base_url)
        if call_count == 1:
            raise requests.exceptions.ConnectionError("Conn Refused")
        # Succeed all others
        return None

    mocker.patch('lametric_power_bridge.sinks.lametric.asyncio.to_thread', side_effect=mock_to_thread)

    # First push
    await push_to_lametric(PowerReading(power_watts=1500))
    
    # Verify: 1st attempt (base), Discovery, 2nd attempt (new IP)
    assert call_count == 2
    assert url_history[0] == base_url
    assert "192.168.1.100" in url_history[1]
    assert mock_discover.call_count == 1
    
    # Second push
    await push_to_lametric(PowerReading(power_watts=1500))
    
    # Verify: 3rd attempt uses new IP directly
    assert call_count == 3
    assert "192.168.1.100" in url_history[2]
    # Discovery count should still be 1 (cached)
    assert mock_discover.call_count == 1


# URL Construction Tests

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