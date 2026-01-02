"""P1 Serial ingress module - reads DSMR telegrams via USB serial port"""
import asyncio
import logging
import re
import sys
from typing import AsyncIterator, Optional

try:
    import serial
except ImportError:
    serial = None

from sources.base import PowerReading

logger = logging.getLogger(__name__)


class P1SerialSource:
    """
    P1 Serial power source.

    Reads DSMR telegrams directly from the smart meter's P1 port
    via USB serial connection. Parses power consumption and production
    in real-time without cloud dependencies.

    Supports DSMR v4+ (115200 baud) and DSMR v2/v3 (9600 baud).
    """

    # OBIS codes for power readings
    OBIS_CONSUMPTION = "1-0:1.7.0"  # Current consumption (kW)
    OBIS_PRODUCTION = "1-0:2.7.0"   # Current production (kW)

    def __init__(
        self,
        device: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        timeout: float = 10.0,
        max_retries: int = 5
    ):
        """
        Initialize P1 Serial source.

        Args:
            device: Serial device path (default: /dev/ttyUSB0)
            baudrate: Serial baudrate - 115200 for DSMR v4+, 9600 for v2/v3 (default: 115200)
            timeout: Read timeout in seconds (default: 10.0)
            max_retries: Maximum consecutive read failures before giving up (default: 5)
        """
        if serial is None:
            logger.error("pyserial library not installed. Run: pip install pyserial")
            sys.exit(1)

        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self.max_retries = max_retries
        self.ser = None

    async def __aenter__(self):
        """Context manager entry: connect to serial port"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: cleanup resources"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("P1 Serial: Port closed")

    async def connect(self) -> None:
        """
        Phase 1: Serial Bootstrap.
        Opens the serial port and validates that we can read DSMR telegrams.
        """
        if not self.device:
            logger.error("P1_SERIAL_DEVICE not configured")
            sys.exit(1)
            return  # For test mocking

        try:
            logger.info(f"P1 Serial: Opening {self.device} at {self.baudrate} baud")

            # Open serial port (blocking, but fast)
            self.ser = serial.Serial(
                port=self.device,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )

            # Verify we can read a telegram
            logger.info("P1 Serial: Testing connection by reading one telegram...")
            telegram = await self._read_telegram()

            if not telegram:
                logger.error("P1 Serial: No data received from device. Check cable and meter configuration.")
                self.ser.close()
                sys.exit(1)
                return

            logger.info(f"P1 Serial: Connection successful. Telegram received ({len(telegram)} lines)")

        except serial.SerialException as e:
            logger.error(f"P1 Serial: Cannot open {self.device}: {e}")
            logger.error("Check that device exists and you have permissions (add user to 'dialout' group)")
            sys.exit(1)
            return
        except Exception as e:
            logger.error(f"P1 Serial: Bootstrap failed: {e}")
            if self.ser:
                self.ser.close()
            sys.exit(1)
            return

    async def stream(self) -> AsyncIterator[PowerReading]:
        """
        Phase 2: Serial Reading Stream.

        Continuously reads DSMR telegrams from the serial port.
        Parses power consumption and production, yields PowerReading objects.

        Auto-reconnects on USB disconnect or read errors.
        """
        if self.ser is None or not self.ser.is_open:
            logger.error("P1 Serial: stream() called before connect()")
            return

        consecutive_errors = 0
        logger.info(f"P1 Serial: Streaming telegrams from {self.device}")

        while True:
            try:
                telegram = await self._read_telegram()

                if not telegram:
                    consecutive_errors += 1
                    if consecutive_errors >= self.max_retries:
                        logger.error(f"P1 Serial: Max retries ({self.max_retries}) exceeded. No data from device.")
                        break

                    logger.warning(f"P1 Serial: No telegram received. Retrying... ({consecutive_errors}/{self.max_retries})")
                    await asyncio.sleep(1)
                    continue

                # Parse power from telegram
                power_reading = self._parse_power(telegram)

                if power_reading:
                    consecutive_errors = 0  # Reset on success
                    yield power_reading
                else:
                    logger.debug("P1 Serial: No power data in telegram (meter initializing?)")

            except serial.SerialException as e:
                consecutive_errors += 1
                if consecutive_errors >= self.max_retries:
                    logger.error(f"P1 Serial: Max retries ({self.max_retries}) exceeded. Last error: {e}")
                    break

                logger.warning(
                    f"P1 Serial: Read error: {e}. "
                    f"Retrying in 2s... ({consecutive_errors}/{self.max_retries})"
                )
                await asyncio.sleep(2)

                # Attempt to reopen port on disconnect
                if not self.ser.is_open:
                    try:
                        self.ser.open()
                        logger.info("P1 Serial: Port reopened successfully")
                    except Exception as reopen_error:
                        logger.error(f"P1 Serial: Cannot reopen port: {reopen_error}")

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= self.max_retries:
                    logger.error(f"P1 Serial: Max retries exceeded. Last error: {e}")
                    break

                logger.error(
                    f"P1 Serial: Unexpected error: {e}. "
                    f"Retrying in 2s... ({consecutive_errors}/{self.max_retries})"
                )
                await asyncio.sleep(2)

    async def _read_telegram(self) -> Optional[list[str]]:
        """
        Read one complete DSMR telegram from serial port.

        A telegram starts with '/' and ends with '!xxxx' (CRC).
        Returns list of lines, or None if read fails.
        """
        telegram = []
        in_telegram = False

        # Run blocking serial read in executor to not block event loop
        loop = asyncio.get_event_loop()

        while True:
            try:
                # Read one line (blocking call, run in executor)
                line = await loop.run_in_executor(None, self.ser.readline)
                line = line.decode('ascii', errors='ignore').strip()

                if not line:
                    continue

                # Start of telegram
                if line.startswith('/'):
                    in_telegram = True
                    telegram = [line]
                    continue

                if in_telegram:
                    telegram.append(line)

                    # End of telegram (CRC line)
                    if line.startswith('!'):
                        # Validate CRC
                        if self._validate_crc(telegram):
                            return telegram
                        else:
                            logger.warning("P1 Serial: CRC validation failed, discarding telegram")
                            telegram = []
                            in_telegram = False

            except Exception as e:
                logger.debug(f"P1 Serial: Read error in telegram: {e}")
                return None

    def _validate_crc(self, telegram: list[str]) -> bool:
        """
        Validate CRC16 checksum of DSMR telegram.

        The last line should be '!xxxx' where xxxx is 4 hex digits.
        CRC is calculated over all bytes from '/' up to and including '!'.
        """
        if not telegram or not telegram[-1].startswith('!'):
            return False

        try:
            # Extract CRC from telegram
            crc_line = telegram[-1]
            if len(crc_line) < 5:
                return False

            telegram_crc = int(crc_line[1:5], 16)

            # Reconstruct telegram string for CRC calculation
            telegram_str = '\r\n'.join(telegram[:-1]) + '\r\n!'

            # Calculate CRC16
            calculated_crc = self._calculate_crc16(telegram_str.encode('ascii'))

            return calculated_crc == telegram_crc

        except (ValueError, IndexError):
            return False

    @staticmethod
    def _calculate_crc16(data: bytes) -> int:
        """
        Calculate CRC16 checksum for DSMR telegram.
        Uses polynomial 0xA001 (reversed 0x8005).
        """
        crc = 0x0000
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def _parse_power(self, telegram: list[str]) -> Optional[PowerReading]:
        """
        Parse power consumption/production from DSMR telegram.

        Extracts:
        - 1-0:1.7.0: Current consumption (kW)
        - 1-0:2.7.0: Current production (kW)

        Net power = consumption - production (positive = consuming, negative = producing)
        """
        consumption_kw = None
        production_kw = None

        # Regex to match OBIS codes: "1-0:1.7.0(00.424*kW)" or "1-0:1.7.0(00.424)"
        obis_pattern = re.compile(r'([\d\-:\.]+)\(([0-9\.]+)(?:\*k?W)?\)')

        for line in telegram:
            match = obis_pattern.search(line)
            if match:
                obis_code = match.group(1)
                value = float(match.group(2))

                if obis_code == self.OBIS_CONSUMPTION:
                    consumption_kw = value
                elif obis_code == self.OBIS_PRODUCTION:
                    production_kw = value

        # Calculate net power (in Watts)
        if consumption_kw is not None or production_kw is not None:
            consumption_w = (consumption_kw or 0.0) * 1000
            production_w = (production_kw or 0.0) * 1000
            net_power_w = consumption_w - production_w

            return PowerReading(
                power_watts=net_power_w,
                timestamp=None  # DSMR telegrams don't include timestamps
            )

        return None
