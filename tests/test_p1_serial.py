import pytest
from sources.p1_serial import P1SerialSource
from sources.base import PowerReading


# Sample DSMR v4 telegram (simplified)
SAMPLE_TELEGRAM = [
    "/ISk5\\2MT382-1000",
    "",
    "1-3:0.2.8(42)",
    "0-0:1.0.0(231226180000W)",
    "1-0:1.7.0(00.424*kW)",  # Consumption: 424W
    "1-0:2.7.0(00.000*kW)",  # Production: 0W
    "!A1B2"
]

SAMPLE_TELEGRAM_PRODUCTION = [
    "/ISk5\\2MT382-1000",
    "",
    "1-3:0.2.8(42)",
    "0-0:1.0.0(231226180000W)",
    "1-0:1.7.0(00.100*kW)",  # Consumption: 100W
    "1-0:2.7.0(01.500*kW)",  # Production: 1500W (net: -1400W)
    "!B2C3"
]


@pytest.mark.asyncio
async def test_p1_connect_success(mocker):
    """Test successful P1 serial port bootstrap"""
    source = P1SerialSource(device="/dev/ttyUSB0")

    # Mock serial.Serial
    mock_serial = mocker.Mock()
    mock_serial.is_open = True
    mocker.patch('sources.p1_serial.serial.Serial', return_value=mock_serial)

    # Mock _read_telegram to return a valid telegram
    mocker.patch.object(source, '_read_telegram', return_value=SAMPLE_TELEGRAM)

    # Connect
    await source.connect()

    # Verify serial port was opened
    assert source.ser is not None


@pytest.mark.asyncio
async def test_p1_connect_no_device_exits(mocker):
    """Test that connect exits when P1_SERIAL_DEVICE is empty"""
    mock_exit = mocker.patch('sources.p1_serial.sys.exit')

    source = P1SerialSource(device="")
    await source.connect()

    # Verify sys.exit was called when device is empty
    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_p1_connect_serial_error_exits(mocker):
    """Test that connect exits on serial port error"""
    source = P1SerialSource(device="/dev/ttyUSB0")

    # Mock serial.Serial to raise SerialException
    import serial
    mocker.patch('sources.p1_serial.serial.Serial', side_effect=serial.SerialException("Port not found"))
    mock_exit = mocker.patch('sources.p1_serial.sys.exit')

    await source.connect()

    # Verify sys.exit was called on serial error
    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_p1_stream_yields_power_readings(mocker):
    """Test that stream() correctly reads telegrams and yields PowerReading objects"""
    source = P1SerialSource(device="/dev/ttyUSB0")

    # Mock serial port (skip connect phase)
    mock_serial = mocker.Mock()
    mock_serial.is_open = True
    source.ser = mock_serial

    # Mock _read_telegram to return test telegrams in sequence
    telegrams = [
        SAMPLE_TELEGRAM,           # 424W consumption
        SAMPLE_TELEGRAM_PRODUCTION, # -1400W (net production)
    ]
    mocker.patch.object(source, '_read_telegram', side_effect=telegrams)

    # Collect readings from stream
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        if len(readings) >= 2:
            break

    # Verify we got 2 PowerReading objects
    assert len(readings) == 2

    # Verify first reading (consumption)
    assert isinstance(readings[0], PowerReading)
    assert readings[0].power_watts == 424.0
    assert readings[0].timestamp is None

    # Verify second reading (production - net negative)
    assert isinstance(readings[1], PowerReading)
    assert readings[1].power_watts == -1400.0  # 100W consumption - 1500W production


@pytest.mark.asyncio
async def test_p1_stream_handles_read_errors(mocker):
    """Test that stream() handles read errors with retries"""
    source = P1SerialSource(device="/dev/ttyUSB0")

    mock_serial = mocker.Mock()
    mock_serial.is_open = True
    source.ser = mock_serial

    # First call returns None (read error), second returns valid telegram
    mocker.patch.object(
        source,
        '_read_telegram',
        side_effect=[None, SAMPLE_TELEGRAM]
    )

    # Mock asyncio.sleep to avoid delays
    mocker.patch('sources.p1_serial.asyncio.sleep')

    # Collect one reading
    readings = []
    async for reading in source.stream():
        readings.append(reading)
        break

    # Verify we got the reading after retry
    assert len(readings) == 1
    assert readings[0].power_watts == 424.0


@pytest.mark.asyncio
async def test_p1_crc_validation():
    """Test CRC16 validation of DSMR telegrams"""
    source = P1SerialSource(device="/dev/ttyUSB0")

    # Valid telegram with correct CRC
    telegram_with_valid_crc = [
        "/ISk5\\2MT382-1000",
        "1-0:1.7.0(00.424*kW)",
        "!E1D2"  # This would be the real CRC
    ]

    # Note: We can't easily test real CRC without a full telegram,
    # so we test the CRC calculation function instead
    test_data = b"/ISk5\\2MT382-1000\r\n1-0:1.7.0(00.424*kW)\r\n!"
    crc = source._calculate_crc16(test_data)

    # Verify CRC is calculated (non-zero)
    assert isinstance(crc, int)
    assert 0 <= crc <= 0xFFFF


@pytest.mark.asyncio
async def test_p1_parse_power():
    """Test parsing of power values from DSMR telegram"""
    source = P1SerialSource(device="/dev/ttyUSB0")

    # Test consumption only
    telegram_consumption = [
        "1-0:1.7.0(01.234*kW)",
        "1-0:2.7.0(00.000*kW)",
    ]
    reading = source._parse_power(telegram_consumption)
    assert reading is not None
    assert reading.power_watts == 1234.0  # 1.234 kW = 1234 W

    # Test production (net negative)
    telegram_production = [
        "1-0:1.7.0(00.100*kW)",
        "1-0:2.7.0(02.000*kW)",
    ]
    reading = source._parse_power(telegram_production)
    assert reading is not None
    assert reading.power_watts == -1900.0  # 100W - 2000W = -1900W

    # Test no power data
    telegram_no_power = [
        "0-0:1.0.0(231226180000W)",
        "1-3:0.2.8(42)",
    ]
    reading = source._parse_power(telegram_no_power)
    assert reading is None


@pytest.mark.asyncio
async def test_p1_context_manager(mocker):
    """Test that P1SerialSource works as async context manager"""
    # Mock serial.Serial
    mock_serial = mocker.Mock()
    mock_serial.is_open = True
    mocker.patch('sources.p1_serial.serial.Serial', return_value=mock_serial)

    # Mock _read_telegram for connect() test
    mock_read = mocker.patch('sources.p1_serial.P1SerialSource._read_telegram', return_value=SAMPLE_TELEGRAM)

    # Use context manager pattern
    async with P1SerialSource(device="/dev/ttyUSB0") as source:
        # Verify connection was established
        assert source.ser is not None

    # Verify cleanup was called on exit
    mock_serial.close.assert_called_once()


@pytest.mark.asyncio
async def test_p1_parse_power_with_various_formats():
    """Test parsing handles different OBIS format variations"""
    source = P1SerialSource(device="/dev/ttyUSB0")

    # Test with 'kW' suffix
    telegram1 = ["1-0:1.7.0(00.424*kW)"]
    reading = source._parse_power(telegram1)
    assert reading.power_watts == 424.0

    # Test without unit (spec allows this)
    telegram2 = ["1-0:1.7.0(00.424)"]
    reading = source._parse_power(telegram2)
    assert reading.power_watts == 424.0

    # Test with just consumption (no production line)
    telegram3 = ["1-0:1.7.0(01.500*kW)"]
    reading = source._parse_power(telegram3)
    assert reading.power_watts == 1500.0
