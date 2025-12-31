import pytest
import json
from sources.homewizard_v2 import HomeWizardV2Source
from sources.base import PowerReading


@pytest.mark.asyncio
async def test_homewizard_v2_connect_success():
    """Test successful HomeWizard v2 connection validation"""
    source = HomeWizardV2Source(host="192.168.2.87", token="test-token-123")

    # Connect should validate config without errors
    await source.connect()

    # Verify config was accepted
    assert source.host == "192.168.2.87"
    assert source.token == "test-token-123"
    assert source.ws_url == "ws://192.168.2.87/api/ws"


@pytest.mark.asyncio
async def test_homewizard_v2_connect_no_host_exits(mocker):
    """Test that connect exits when HOMEWIZARD_HOST is empty"""
    mock_exit = mocker.patch('sources.homewizard_v2.sys.exit')

    source = HomeWizardV2Source(host="", token="test-token")
    await source.connect()

    # Verify sys.exit was called when host is empty
    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_homewizard_v2_connect_no_token_exits(mocker):
    """Test that connect exits when HOMEWIZARD_TOKEN is empty"""
    mock_exit = mocker.patch('sources.homewizard_v2.sys.exit')

    source = HomeWizardV2Source(host="192.168.2.87", token="")
    await source.connect()

    # Verify sys.exit was called when token is empty
    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_homewizard_v2_stream_yields_power_readings(mocker):
    """Test that stream() correctly handles WebSocket auth and yields PowerReading objects"""
    source = HomeWizardV2Source(host="192.168.2.87", token="test-token-123")

    # Mock WebSocket messages
    mock_messages = [
        # Auth request from device
        json.dumps({"type": "authorization_requested", "data": {"api_version": "2.0.0"}}),
        # Auth confirmation
        json.dumps({"type": "authorized"}),
        # Power measurements
        json.dumps({"type": "measurement", "data": {"active_power_w": 1500}}),
        json.dumps({"type": "measurement", "data": {"active_power_w": -500}}),
        json.dumps({"type": "measurement", "data": {"active_power_w": 0}}),
    ]

    # Mock websocket connection
    mock_websocket = mocker.AsyncMock()
    mock_websocket.recv.side_effect = mock_messages[:2]  # Auth messages first

    # Make websocket async iterable for remaining messages
    async def mock_message_iterator():
        for msg in mock_messages[2:]:
            yield msg

    mock_websocket.__aiter__ = lambda self: mock_message_iterator()

    # Mock the websockets.connect to yield our mock websocket once
    async def mock_connect(*args, **kwargs):
        yield mock_websocket

    mocker.patch('sources.homewizard_v2.websockets.connect', side_effect=mock_connect)

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
    assert readings[0].timestamp is None  # v2 API doesn't provide timestamps

    # Verify second reading (producing power)
    assert isinstance(readings[1], PowerReading)
    assert readings[1].power_watts == -500.0

    # Verify third reading (neutral)
    assert isinstance(readings[2], PowerReading)
    assert readings[2].power_watts == 0.0

    # Verify auth message was sent
    mock_websocket.send.assert_any_call(
        json.dumps({"type": "authorization", "data": "test-token-123"})
    )

    # Verify subscription message was sent
    mock_websocket.send.assert_any_call(
        json.dumps({"type": "subscribe", "data": "measurement"})
    )


@pytest.mark.asyncio
async def test_homewizard_v2_stream_handles_auth_failure(mocker):
    """Test that stream() handles authentication failure gracefully"""
    import asyncio

    source = HomeWizardV2Source(host="192.168.2.87", token="wrong-token")

    # Mock WebSocket messages - auth failure scenario
    mock_messages = [
        # Auth request from device
        json.dumps({"type": "authorization_requested", "data": {"api_version": "2.0.0"}}),
        # Auth error response
        json.dumps({"type": "error", "data": {"error": "Invalid token"}}),
    ]

    # Mock websocket connection
    mock_websocket = mocker.AsyncMock()
    mock_websocket.recv.side_effect = mock_messages

    async def mock_connect(*args, **kwargs):
        yield mock_websocket

    mocker.patch('sources.homewizard_v2.websockets.connect', side_effect=mock_connect)

    # Mock sleep to avoid actual delays
    mock_sleep = mocker.patch('sources.homewizard_v2.asyncio.sleep')

    # Try to collect readings with a timeout (should fail auth and retry)
    readings = []
    try:
        async def collect_readings():
            async for reading in source.stream():
                readings.append(reading)

        # Use wait_for with short timeout to prevent infinite loop
        await asyncio.wait_for(collect_readings(), timeout=0.1)
    except asyncio.TimeoutError:
        pass  # Expected - auth keeps failing and we time out

    # Verify no readings were yielded (auth failed)
    assert len(readings) == 0

    # Verify auth response was sent
    mock_websocket.send.assert_called_with(
        json.dumps({"type": "authorization", "data": "wrong-token"})
    )

    # Verify sleep was called (retry delay after auth failure)
    assert mock_sleep.call_count >= 1


@pytest.mark.asyncio
async def test_homewizard_v2_stream_missing_active_power_field(mocker):
    """Test that stream() handles missing active_power_w field gracefully"""
    source = HomeWizardV2Source(host="192.168.2.87", token="test-token-123")

    # Mock WebSocket messages
    mock_messages = [
        # Auth flow
        json.dumps({"type": "authorization_requested", "data": {"api_version": "2.0.0"}}),
        json.dumps({"type": "authorized"}),
        # Measurement without active_power_w (device initializing)
        json.dumps({"type": "measurement", "data": {"wifi_ssid": "MyNetwork"}}),
        # Valid measurement
        json.dumps({"type": "measurement", "data": {"active_power_w": 999}}),
    ]

    # Mock websocket connection
    mock_websocket = mocker.AsyncMock()
    mock_websocket.recv.side_effect = mock_messages[:2]

    async def mock_message_iterator():
        for msg in mock_messages[2:]:
            yield msg

    mock_websocket.__aiter__ = lambda self: mock_message_iterator()

    async def mock_connect(*args, **kwargs):
        yield mock_websocket

    mocker.patch('sources.homewizard_v2.websockets.connect', side_effect=mock_connect)

    # Collect readings
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        if len(readings) >= 1:
            break

    # Verify we got the valid reading (first was skipped)
    assert len(readings) == 1
    assert readings[0].power_watts == 999.0


@pytest.mark.asyncio
async def test_homewizard_v2_stream_ignores_unknown_message_types(mocker):
    """Test that stream() ignores unknown message types gracefully"""
    source = HomeWizardV2Source(host="192.168.2.87", token="test-token-123")

    # Mock WebSocket messages with various types
    mock_messages = [
        # Auth flow
        json.dumps({"type": "authorization_requested", "data": {"api_version": "2.0.0"}}),
        json.dumps({"type": "authorized"}),
        # Unknown message types (should be ignored)
        json.dumps({"type": "device", "data": {"product_name": "P1 Meter"}}),
        json.dumps({"type": "system", "data": {"cloud_enabled": False}}),
        # Valid measurement
        json.dumps({"type": "measurement", "data": {"active_power_w": 1234}}),
    ]

    # Mock websocket connection
    mock_websocket = mocker.AsyncMock()
    mock_websocket.recv.side_effect = mock_messages[:2]

    async def mock_message_iterator():
        for msg in mock_messages[2:]:
            yield msg

    mock_websocket.__aiter__ = lambda self: mock_message_iterator()

    async def mock_connect(*args, **kwargs):
        yield mock_websocket

    mocker.patch('sources.homewizard_v2.websockets.connect', side_effect=mock_connect)

    # Collect readings
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        if len(readings) >= 1:
            break

    # Verify we got the measurement (other types ignored)
    assert len(readings) == 1
    assert readings[0].power_watts == 1234.0


@pytest.mark.asyncio
async def test_homewizard_v2_context_manager(mocker):
    """Test that HomeWizardV2Source works as async context manager"""
    source_created = False

    # Use context manager pattern
    async with HomeWizardV2Source(host="192.168.2.87", token="test-token") as source:
        source_created = True
        # Verify connection was validated
        assert source.host == "192.168.2.87"
        assert source.token == "test-token"

    # Verify context manager worked
    assert source_created is True
