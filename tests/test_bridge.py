"""Tests for bridge.py CLI and source selection logic"""

import os
import pytest
import sys
from unittest.mock import patch

from bridge import get_source
from sources.tibber import TibberSource


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
