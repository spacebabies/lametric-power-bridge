"""Tests for mDNS discovery module"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from lametric_power_bridge.sources.discovery_mdns import discover_homewizard_p1, HomeWizardListener, TARGET_PRODUCT_TYPE

@pytest.mark.asyncio
class TestHomeWizardListener:
    """Test the mDNS listener logic"""

    async def test_add_service_finds_target_device(self):
        """Test that listener correctly identifies target device"""
        mock_aiozc = AsyncMock()
        found_event = asyncio.Event()
        listener = HomeWizardListener(mock_aiozc, TARGET_PRODUCT_TYPE, found_event)
        
        # Mock service info
        mock_info = MagicMock()
        mock_info.properties = {
            b"product_type": TARGET_PRODUCT_TYPE.encode("utf-8"),
        }
        mock_info.parsed_addresses.return_value = ["192.168.1.50"]
        
        # Setup async_get_service_info mock
        mock_aiozc.async_get_service_info.return_value = mock_info
        
        # Simulate service discovery
        listener.add_service(MagicMock(), "_hwenergy._tcp.local.", "MyDevice._hwenergy._tcp.local.")
        
        # Since add_service schedules a task, we need to wait for it or yield control
        # Wait for the event to be set
        try:
            await asyncio.wait_for(found_event.wait(), timeout=0.1)
        except asyncio.TimeoutError:
            pytest.fail("Event was not set")

        assert listener.found_ip == "192.168.1.50"
        assert listener.found_name == "MyDevice._hwenergy._tcp.local."

    async def test_add_service_ignores_other_devices(self):
        """Test that listener ignores devices with wrong product type"""
        mock_aiozc = AsyncMock()
        found_event = asyncio.Event()
        listener = HomeWizardListener(mock_aiozc, TARGET_PRODUCT_TYPE, found_event)
        
        mock_info = MagicMock()
        mock_info.properties = {b"product_type": b"HWE-SKT"} # Socket, not P1
        mock_info.parsed_addresses.return_value = ["192.168.1.60"]
        
        mock_aiozc.async_get_service_info.return_value = mock_info
        
        listener.add_service(MagicMock(), "_hwenergy._tcp.local.", "Socket._hwenergy._tcp.local.")
        
        # Wait a bit to ensure task ran
        await asyncio.sleep(0.01)
        
        assert listener.found_ip is None
        assert not found_event.is_set()


@pytest.mark.asyncio
class TestDiscoverHomeWizardP1:
    """Test the main discovery function"""

    @patch("lametric_power_bridge.sources.discovery_mdns.AsyncZeroconf")
    @patch("lametric_power_bridge.sources.discovery_mdns.AsyncServiceBrowser")
    async def test_discovery_success(self, mock_browser, mock_aiozc_cls):
        """Test successful discovery"""
        # Mock AsyncZeroconf instance
        aiozc_instance = AsyncMock()
        mock_aiozc_cls.return_value = aiozc_instance
        
        # Mock listener to simulate finding device
        with patch("lametric_power_bridge.sources.discovery_mdns.HomeWizardListener") as MockListener:
            # We want the real listener logic or a mock that sets the event?
            # If we mock the listener, we need to control the event.
            
            # Let's use side_effect on init to capture the event
            captured_event = None
            def side_effect(aiozc, target, event):
                nonlocal captured_event
                captured_event = event
                instance = MagicMock()
                instance.found_ip = "192.168.1.50"
                return instance
            
            MockListener.side_effect = side_effect
            
            # Run discovery in background
            task = asyncio.create_task(discover_homewizard_p1(timeout=1.0))
            
            # Wait for listener init
            await asyncio.sleep(0.01)
            
            # Simulate device found by setting event
            if captured_event:
                captured_event.set()
            
            ip = await task
            
            assert ip == "192.168.1.50"
            mock_aiozc_cls.assert_called_once()
            aiozc_instance.async_close.assert_called_once()

    @patch("lametric_power_bridge.sources.discovery_mdns.AsyncZeroconf")
    @patch("lametric_power_bridge.sources.discovery_mdns.AsyncServiceBrowser")
    async def test_discovery_timeout(self, mock_browser, mock_aiozc_cls):
        """Test discovery timeout (no device found)"""
        aiozc_instance = AsyncMock()
        mock_aiozc_cls.return_value = aiozc_instance
        
        with patch("lametric_power_bridge.sources.discovery_mdns.HomeWizardListener") as MockListener:
            # Mock listener that never sets event
            listener_instance = MagicMock()
            listener_instance.found_ip = None
            MockListener.return_value = listener_instance
            
            ip = await discover_homewizard_p1(timeout=0.1)
            
            assert ip is None