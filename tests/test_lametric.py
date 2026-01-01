import pytest
from sources.base import PowerReading
from sinks.lametric import LaMetricSink, push_to_lametric, push_to_lametric_stale


@pytest.mark.asyncio
async def test_push_to_lametric_import_power(mocker):
    """Test LaMetric push with importing power"""
    # Mock environment variables
    mocker.patch.dict('os.environ', {
        'LAMETRIC_API_KEY': 'test_key',
        'LAMETRIC_URL': 'http://192.168.1.50:8080/api/v2/device/notifications'
    })

    # Reset global sink instance
    import sinks.lametric
    sinks.lametric._sink_instance = None

    # Mock the HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call the function with importing power
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Verify request was made
    mock_request.assert_called_once()


@pytest.mark.asyncio
async def test_push_to_lametric_export_power(mocker):
    """Test LaMetric push with exporting power"""
    # Mock environment variables
    mocker.patch.dict('os.environ', {
        'LAMETRIC_API_KEY': 'test_key',
        'LAMETRIC_URL': 'http://192.168.1.50:8080/api/v2/device/notifications'
    })

    # Reset global sink instance
    import sinks.lametric
    sinks.lametric._sink_instance = None

    # Mock the HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call the function with exporting power
    reading = PowerReading(power_watts=-500)
    await push_to_lametric(reading)

    # Verify request was made
    assert mock_request.call_count == 1


@pytest.mark.asyncio
async def test_push_to_lametric_round_float(mocker):
    """Test LaMetric push with float value (should be rounded)"""
    # Mock environment variables
    mocker.patch.dict('os.environ', {
        'LAMETRIC_API_KEY': 'test_key',
        'LAMETRIC_URL': 'http://192.168.1.50:8080/api/v2/device/notifications'
    })

    # Reset global sink instance
    import sinks.lametric
    sinks.lametric._sink_instance = None

    # Mock the HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call the function with a float value that needs rounding
    reading = PowerReading(power_watts=180.7)
    await push_to_lametric(reading)

    # Verify request was made
    assert mock_request.call_count == 1


@pytest.mark.asyncio
async def test_push_to_lametric_kilowatts(mocker):
    """Test LaMetric push with high power (kW display)"""
    # Mock environment variables
    mocker.patch.dict('os.environ', {
        'LAMETRIC_API_KEY': 'test_key',
        'LAMETRIC_URL': 'http://192.168.1.50:8080/api/v2/device/notifications'
    })

    # Reset global sink instance
    import sinks.lametric
    sinks.lametric._sink_instance = None

    # Mock the HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call the function with high power (kW display)
    reading = PowerReading(power_watts=10500)
    await push_to_lametric(reading)

    # Verify request was made
    assert mock_request.call_count == 1


@pytest.mark.asyncio
async def test_push_to_lametric_export_high(mocker):
    """Test LaMetric push with high export power (negative kW)"""
    # Mock environment variables
    mocker.patch.dict('os.environ', {
        'LAMETRIC_API_KEY': 'test_key',
        'LAMETRIC_URL': 'http://192.168.1.50:8080/api/v2/device/notifications'
    })

    # Reset global sink instance
    import sinks.lametric
    sinks.lametric._sink_instance = None

    # Mock the HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call the function with high export power (negative kW)
    reading = PowerReading(power_watts=-11000)
    await push_to_lametric(reading)

    # Verify request was made
    assert mock_request.call_count == 1


@pytest.mark.asyncio
async def test_push_to_lametric_stale(mocker):
    """Test LaMetric push with stale data indicator"""
    # Mock environment variables
    mocker.patch.dict('os.environ', {
        'LAMETRIC_API_KEY': 'test_key',
        'LAMETRIC_URL': 'http://192.168.1.50:8080/api/v2/device/notifications'
    })

    # Reset global sink instance
    import sinks.lametric
    sinks.lametric._sink_instance = None

    # Mock the HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Call the stale data function
    await push_to_lametric_stale()

    # Verify request was made
    assert mock_request.call_count == 1


@pytest.mark.asyncio
async def test_lametric_sink_with_manual_url(mocker):
    """Test LaMetric sink with manually configured URL"""
    # Mock HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Create sink with manual URL
    sink = LaMetricSink(
        api_key="test_key",
        url="http://192.168.1.50:8080/api/v2/device/notifications"
    )

    # Push reading
    reading = PowerReading(power_watts=1500)
    await sink.push(reading)

    # Verify no discovery was attempted
    assert sink._discovered_ip is None

    # Verify HTTP request was made
    mock_request.assert_called_once()


@pytest.mark.asyncio
async def test_lametric_sink_with_discovery(mocker):
    """Test LaMetric sink with auto-discovery"""
    # Mock discovery
    mock_discover = mocker.patch(
        'sinks.lametric.discover_lametric',
        return_value="192.168.1.50"
    )

    # Mock HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Create sink without URL (triggers discovery)
    sink = LaMetricSink(api_key="test_key", url=None)

    # Push reading
    reading = PowerReading(power_watts=1500)
    await sink.push(reading)

    # Verify discovery was called
    mock_discover.assert_called_once()

    # Verify URL was constructed
    assert sink.url == "http://192.168.1.50:8080/api/v2/device/notifications"
    assert sink._discovered_ip == "192.168.1.50"


@pytest.mark.asyncio
async def test_lametric_sink_rediscovers_on_connection_error(mocker):
    """Test that sink re-discovers device on connection failure"""
    import requests

    # Mock discovery (returns different IPs on successive calls)
    mock_discover = mocker.patch(
        'sinks.lametric.discover_lametric',
        side_effect=["192.168.1.50", "192.168.1.51"]  # IP changed
    )

    # Mock HTTP request to fail first time, succeed second time
    call_count = [0]

    def mock_request_fn(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise requests.exceptions.ConnectionError("Connection refused")
        # Second call succeeds (after re-discovery)

    mocker.patch('sinks.lametric.asyncio.to_thread', side_effect=mock_request_fn)

    # Create sink without URL
    sink = LaMetricSink(api_key="test_key", url=None)

    # Push reading
    reading = PowerReading(power_watts=1500)
    await sink.push(reading)

    # Verify discovery was called twice (initial + re-discovery)
    assert mock_discover.call_count == 2

    # Verify URL was updated to new IP
    assert sink.url == "http://192.168.1.51:8080/api/v2/device/notifications"
    assert sink._discovered_ip == "192.168.1.51"


@pytest.mark.asyncio
async def test_lametric_sink_backwards_compat_functions(mocker):
    """Test backwards compatible function wrappers"""
    # Set environment variables
    mocker.patch.dict('os.environ', {
        'LAMETRIC_API_KEY': 'test_key',
        'LAMETRIC_URL': 'http://192.168.1.50:8080/api/v2/device/notifications'
    })

    # Reset global sink instance
    import sinks.lametric
    sinks.lametric._sink_instance = None

    # Mock HTTP request
    mock_request = mocker.patch('sinks.lametric.asyncio.to_thread')

    # Test push_to_lametric
    reading = PowerReading(power_watts=1500)
    await push_to_lametric(reading)

    # Test push_to_lametric_stale
    await push_to_lametric_stale()

    # Verify both calls worked
    assert mock_request.call_count == 2
