import pytest
import httpx
from sources.homewizard_v1 import HomeWizardV1Source
from sources.base import PowerReading


@pytest.mark.asyncio
async def test_homewizard_connect_success(mocker):
    """Test successful HomeWizard v1 HTTP bootstrap"""
    # Create source
    source = HomeWizardV1Source(host="192.168.2.87")

    # Mock httpx.AsyncClient
    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "active_power_w": 1500,
        "active_power_l1_w": 500,
        "active_power_l2_w": 600,
        "active_power_l3_w": 400
    }
    mock_response.raise_for_status = mocker.Mock()
    mock_client.get.return_value = mock_response

    # Patch AsyncClient to return our mock
    mocker.patch('sources.homewizard_v1.httpx.AsyncClient', return_value=mock_client)

    # Connect
    await source.connect()

    # Verify client was created and GET request was made
    assert source.client is not None
    mock_client.get.assert_called_once_with("http://192.168.2.87/api/v1/data")


@pytest.mark.asyncio
async def test_homewizard_connect_no_host_exits(mocker):
    """Test that connect exits when HOMEWIZARD_HOST is empty"""
    mock_exit = mocker.patch('sources.homewizard_v1.sys.exit')

    source = HomeWizardV1Source(host="")
    await source.connect()

    # Verify sys.exit was called when host is empty
    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_homewizard_connect_network_error_exits(mocker):
    """Test that connect exits on network error"""
    source = HomeWizardV1Source(host="192.168.2.87")

    # Mock httpx.AsyncClient to raise ConnectError
    mock_client = mocker.AsyncMock()
    mock_client.get.side_effect = mocker.Mock(
        side_effect=Exception("ConnectError")
    )
    mock_client.get.side_effect.__class__.__name__ = "ConnectError"

    # Import httpx to get the real ConnectError
    import httpx
    mock_client.get.side_effect = httpx.ConnectError("Cannot reach host")

    mocker.patch('sources.homewizard_v1.httpx.AsyncClient', return_value=mock_client)
    mock_exit = mocker.patch('sources.homewizard_v1.sys.exit')

    await source.connect()

    # Verify sys.exit was called on connection error
    mock_exit.assert_called_once_with(1)
    mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_homewizard_stream_yields_power_readings(mocker):
    """Test that stream() correctly polls and yields PowerReading objects"""
    source = HomeWizardV1Source(host="192.168.2.87", poll_interval=0.01)  # Fast polling for tests

    # Mock client (skip connect phase)
    mock_client = mocker.AsyncMock()

    # Create a sequence of responses
    mock_responses = [
        {"active_power_w": 1500},  # Consuming
        {"active_power_w": -500},  # Producing
        {"active_power_w": 0},     # Neutral
    ]

    response_objects = []
    for data in mock_responses:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = data
        mock_response.raise_for_status = mocker.Mock()
        response_objects.append(mock_response)

    # Make get() return responses in sequence
    mock_client.get.side_effect = response_objects
    source.client = mock_client

    # Collect readings from stream
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        if len(readings) >= 3:  # Stop after 3 readings
            break

    # Verify we got 3 PowerReading objects
    assert len(readings) == 3

    # Verify first reading (consuming power)
    assert isinstance(readings[0], PowerReading)
    assert readings[0].power_watts == 1500.0
    assert readings[0].timestamp is None  # v1 API doesn't provide timestamps

    # Verify second reading (producing power)
    assert isinstance(readings[1], PowerReading)
    assert readings[1].power_watts == -500.0

    # Verify third reading (neutral)
    assert isinstance(readings[2], PowerReading)
    assert readings[2].power_watts == 0.0

    # Verify GET was called multiple times
    assert mock_client.get.call_count == 3


@pytest.mark.asyncio
async def test_homewizard_stream_handles_device_busy(mocker):
    """Test that stream() handles device busy (503) with exponential backoff"""
    source = HomeWizardV1Source(host="192.168.2.87", poll_interval=0.01)

    mock_client = mocker.AsyncMock()

    # First response: device busy (503)
    mock_busy_response = mocker.Mock()
    mock_busy_response.status_code = 503

    # Second response: success
    mock_success_response = mocker.Mock()
    mock_success_response.status_code = 200
    mock_success_response.json.return_value = {"active_power_w": 1234}
    mock_success_response.raise_for_status = mocker.Mock()

    mock_client.get.side_effect = [mock_busy_response, mock_success_response]
    source.client = mock_client

    # Mock asyncio.sleep to avoid actual delays
    mock_sleep = mocker.patch('sources.homewizard_v1.asyncio.sleep')

    # Collect one reading
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        break

    # Verify we got the reading after retry
    assert len(readings) == 1
    assert readings[0].power_watts == 1234.0

    # Verify sleep was called (retry delay)
    assert mock_sleep.call_count >= 1


@pytest.mark.asyncio
async def test_homewizard_stream_missing_active_power_field(mocker):
    """Test that stream() handles missing active_power_w field gracefully"""
    source = HomeWizardV1Source(host="192.168.2.87", poll_interval=0.01)

    mock_client = mocker.AsyncMock()

    # Response without active_power_w (device initializing)
    mock_response_1 = mocker.Mock()
    mock_response_1.status_code = 200
    mock_response_1.json.return_value = {"wifi_ssid": "MyNetwork"}  # Other fields but no power
    mock_response_1.raise_for_status = mocker.Mock()

    # Second response with power
    mock_response_2 = mocker.Mock()
    mock_response_2.status_code = 200
    mock_response_2.json.return_value = {"active_power_w": 999}
    mock_response_2.raise_for_status = mocker.Mock()

    mock_client.get.side_effect = [mock_response_1, mock_response_2]
    source.client = mock_client

    # Mock sleep
    mocker.patch('sources.homewizard_v1.asyncio.sleep')

    # Collect readings
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        if len(readings) >= 1:
            break

    # Verify we got the second reading (first was skipped)
    assert len(readings) == 1
    assert readings[0].power_watts == 999.0


@pytest.mark.asyncio
async def test_homewizard_context_manager(mocker):
    """Test that HomeWizardV1Source works as async context manager"""
    # Mock httpx.AsyncClient
    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"active_power_w": 1500}
    mock_response.raise_for_status = mocker.Mock()
    mock_client.get.return_value = mock_response

    mocker.patch('sources.homewizard_v1.httpx.AsyncClient', return_value=mock_client)

    # Use context manager pattern
    async with HomeWizardV1Source(host="192.168.2.87") as source:
        # Verify connection was established
        assert source.client is not None
        mock_client.get.assert_called_once_with("http://192.168.2.87/api/v1/data")

    # Verify cleanup was called on exit
    mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_homewizard_connect_with_discovery(mocker):
    """Test HomeWizard v1 connection with auto-discovery"""
    # Create source without host (triggers discovery)
    source = HomeWizardV1Source(host=None)

    # Mock discovery
    mock_discover = mocker.patch(
        'sources.homewizard_v1.discover_homewizard',
        return_value="192.168.1.87"
    )

    # Mock httpx.AsyncClient
    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"active_power_w": 1500}
    mock_response.raise_for_status = mocker.Mock()
    mock_client.get.return_value = mock_response

    mocker.patch('sources.homewizard_v1.httpx.AsyncClient', return_value=mock_client)

    # Connect
    await source.connect()

    # Verify discovery was called
    mock_discover.assert_called_once()

    # Verify host was set to discovered IP
    assert source.host == "192.168.1.87"
    assert source.base_url == "http://192.168.1.87/api/v1/data"


@pytest.mark.asyncio
async def test_homewizard_connect_discovery_failure_exits(mocker):
    """Test that connect exits when discovery fails"""
    source = HomeWizardV1Source(host=None)

    # Mock discovery failure (returns None)
    mocker.patch('sources.homewizard_v1.discover_homewizard', return_value=None)
    mock_exit = mocker.patch('sources.homewizard_v1.sys.exit')

    await source.connect()

    # Verify sys.exit was called
    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_homewizard_stream_rediscovers_on_ip_change(mocker):
    """Test that stream re-discovers device when IP changes"""
    source = HomeWizardV1Source(host="192.168.1.87", poll_interval=0.01)

    # Mock client
    mock_client = mocker.AsyncMock()

    # First 3 calls fail (ConnectError)
    mock_client.get.side_effect = [
        httpx.ConnectError("Connection refused"),
        httpx.ConnectError("Connection refused"),
        httpx.ConnectError("Connection refused"),
        # After re-discovery, success
        mocker.Mock(
            status_code=200,
            json=lambda: {"active_power_w": 999},
            raise_for_status=mocker.Mock()
        )
    ]

    source.client = mock_client

    # Mock re-discovery returning new IP
    mock_discover = mocker.patch(
        'sources.homewizard_v1.discover_homewizard',
        return_value="192.168.1.88"  # New IP
    )

    # Mock sleep
    mocker.patch('sources.homewizard_v1.asyncio.sleep')

    # Collect one reading
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        break

    # Verify re-discovery was triggered
    mock_discover.assert_called_once()

    # Verify host was updated
    assert source.host == "192.168.1.88"
    assert source.base_url == "http://192.168.1.88/api/v1/data"

    # Verify we got the reading after recovery
    assert len(readings) == 1
    assert readings[0].power_watts == 999.0
