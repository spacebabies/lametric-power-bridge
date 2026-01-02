"""Tests for bridge.py CLI and source selection logic"""

import os
import pytest
import sys
from unittest.mock import patch

from bridge import get_source
from sources.tibber import TibberSource
from sources.p1_serial import P1SerialSource


class TestGetSource:
    """Test the get_source() factory function"""

    def test_get_source_tibber_success(self, monkeypatch):
        """Test Tibber source initialization with valid token"""
        monkeypatch.setenv("TIBBER_TOKEN", "test_token_123")

        source = get_source("tibber")

        assert isinstance(source, TibberSource)
        assert source.token == "test_token_123"

    def test_get_source_tibber_missing_token_exits(self, monkeypatch):
        """Test Tibber source fails when TIBBER_TOKEN is missing"""
        monkeypatch.delenv("TIBBER_TOKEN", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            get_source("tibber")

        assert exc_info.value.code == 1

    def test_get_source_unknown_source_exits(self, monkeypatch):
        """Test unknown source name causes hard fail"""
        with pytest.raises(SystemExit) as exc_info:
            get_source("invalid_source")

        assert exc_info.value.code == 1

    def test_get_source_p1_serial_success(self, monkeypatch):
        """Test P1 Serial source initialization with valid device"""
        monkeypatch.setenv("P1_SERIAL_DEVICE", "/dev/ttyUSB0")
        monkeypatch.setenv("P1_SERIAL_BAUDRATE", "115200")

        source = get_source("p1-serial")

        assert isinstance(source, P1SerialSource)
        assert source.device == "/dev/ttyUSB0"
        assert source.baudrate == 115200

    def test_get_source_p1_serial_defaults(self, monkeypatch):
        """Test P1 Serial source uses defaults when env vars not set"""
        monkeypatch.delenv("P1_SERIAL_DEVICE", raising=False)
        monkeypatch.delenv("P1_SERIAL_BAUDRATE", raising=False)

        source = get_source("p1-serial")

        assert isinstance(source, P1SerialSource)
        assert source.device == "/dev/ttyUSB0"  # Default
        assert source.baudrate == 115200  # Default
