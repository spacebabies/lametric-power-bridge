import pytest
from sources.tibber import TibberSource
from sources.base import PowerReading


@pytest.mark.asyncio
async def test_tibber_connect_success(mocker):
    """Test successful Tibber HTTP bootstrap"""
    # Mock the requests.post call
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        'data': {
            'viewer': {
                'websocketSubscriptionUrl': 'wss://api.tibber.com/v1-beta/gql/subscriptions',
                'homes': [
                    {
                        'id': 'test-home-123',
                        'appNickname': 'Test Home',
                        'features': {
                            'realTimeConsumptionEnabled': True
                        }
                    }
                ]
            }
        }
    }
    mock_post = mocker.patch('sources.tibber.requests.post', return_value=mock_response)

    # Create source and connect
    source = TibberSource(token='test-token')
    await source.connect()

    # Verify HTTP call was made
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert 'Bearer test-token' in call_args[1]['headers']['Authorization']

    # Verify internal state was set correctly
    assert source.wss_url == 'wss://api.tibber.com/v1-beta/gql/subscriptions'
    assert source.home_id == 'test-home-123'


@pytest.mark.asyncio
async def test_tibber_connect_no_pulse_exits(mocker):
    """Test that connect exits when no Pulse is found"""
    # Mock response with no realTimeConsumptionEnabled homes
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        'data': {
            'viewer': {
                'websocketSubscriptionUrl': 'wss://api.tibber.com/v1-beta/gql/subscriptions',
                'homes': [
                    {
                        'id': 'test-home-123',
                        'appNickname': 'Test Home',
                        'features': {
                            'realTimeConsumptionEnabled': False  # No Pulse!
                        }
                    }
                ]
            }
        }
    }
    mocker.patch('sources.tibber.requests.post', return_value=mock_response)
    mock_exit = mocker.patch('sources.tibber.sys.exit')

    source = TibberSource(token='test-token')
    await source.connect()

    # Verify sys.exit was called when no Pulse found
    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_tibber_stream_yields_power_readings(mocker):
    """Test that stream() correctly parses WebSocket messages and yields PowerReading"""
    source = TibberSource(token='test-token')
    source.wss_url = 'wss://test.example.com'
    source.home_id = 'test-home-123'

    # Mock WebSocket messages
    mock_websocket_messages = [
        '{"type": "connection_ack"}',
        '{"type": "next", "payload": {"data": {"liveMeasurement": {"power": 1500, "timestamp": "2025-12-26T18:00:00"}}}}',
        '{"type": "next", "payload": {"data": {"liveMeasurement": {"power": -500, "timestamp": "2025-12-26T18:01:00"}}}}',
        '{"type": "complete"}',
    ]

    # Create a mock async iterator for websocket messages
    class MockWebSocket:
        def __init__(self, messages):
            self.messages = iter(messages)
            self.sent = []

        async def send(self, msg):
            self.sent.append(msg)

        async def recv(self):
            return next(self.messages)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.messages)
            except StopIteration:
                raise StopAsyncIteration

    # Mock websockets.connect to return our mock
    mock_ws = MockWebSocket(mock_websocket_messages)

    async def mock_connect(*args, **kwargs):
        yield mock_ws

    mocker.patch('sources.tibber.websockets.connect', side_effect=mock_connect)

    # Collect readings from stream
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        if len(readings) >= 2:  # Stop after 2 readings
            break

    # Verify we got 2 PowerReading objects
    assert len(readings) == 2

    # Verify first reading (consuming power)
    assert isinstance(readings[0], PowerReading)
    assert readings[0].power_watts == 1500
    assert readings[0].timestamp == "2025-12-26T18:00:00"

    # Verify second reading (producing power)
    assert isinstance(readings[1], PowerReading)
    assert readings[1].power_watts == -500
    assert readings[1].timestamp == "2025-12-26T18:01:00"
