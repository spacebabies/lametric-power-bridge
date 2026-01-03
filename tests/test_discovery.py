"""Tests for mDNS discovery module"""
import time
from unittest.mock import MagicMock, patch

from sources.discovery_mdns import discover_homewizard_p1, HomeWizardListener, TARGET_PRODUCT_TYPE


class TestHomeWizardListener:
    """Test the mDNS listener logic"""

    def test_add_service_finds_target_device(self):
        """Test that listener correctly identifies target device"""
        listener = HomeWizardListener()
        mock_zc = MagicMock()
        
        # Mock service info
        mock_info = MagicMock()
        # Properties as bytes
        mock_info.properties = {
            b"product_type": TARGET_PRODUCT_TYPE.encode("utf-8"),
            b"other_field": b"value"
        }
        mock_info.parsed_addresses.return_value = ["192.168.1.50"]
        
        mock_zc.get_service_info.return_value = mock_info
        
        # Simulate service discovery
        listener.add_service(mock_zc, "_hwenergy._tcp.local.", "MyDevice._hwenergy._tcp.local.")
        
        assert listener.found_ip == "192.168.1.50"
        assert listener.found_name == "MyDevice._hwenergy._tcp.local."

    def test_add_service_ignores_other_devices(self):
        """Test that listener ignores devices with wrong product type"""
        listener = HomeWizardListener()
        mock_zc = MagicMock()
        
        mock_info = MagicMock()
        mock_info.properties = {b"product_type": b"HWE-SKT"} # Socket, not P1
        mock_info.parsed_addresses.return_value = ["192.168.1.60"]
        
        mock_zc.get_service_info.return_value = mock_info
        
        listener.add_service(mock_zc, "_hwenergy._tcp.local.", "Socket._hwenergy._tcp.local.")
        
        assert listener.found_ip is None


class TestDiscoverHomeWizardP1:
    """Test the main discovery function"""

    @patch("sources.discovery_mdns.Zeroconf")
    @patch("sources.discovery_mdns.ServiceBrowser")
    def test_discovery_success(self, mock_browser, mock_zc):
        """Test successful discovery"""
        # Mock Zeroconf instance
        zc_instance = MagicMock()
        mock_zc.return_value = zc_instance
        
        # Create a real listener but inject result immediately
        with patch("sources.discovery_mdns.HomeWizardListener") as MockListener:
            listener_instance = MockListener.return_value
            listener_instance.found_ip = "192.168.1.50"
            
            ip = discover_homewizard_p1(timeout=1.0)
            
            assert ip == "192.168.1.50"
            mock_zc.assert_called_once()

    @patch("sources.discovery_mdns.Zeroconf")
    @patch("sources.discovery_mdns.ServiceBrowser")
    def test_discovery_timeout(self, mock_browser, mock_zc):
        """Test discovery timeout (no device found)"""
        zc_instance = MagicMock()
        mock_zc.return_value = zc_instance
        
        with patch("sources.discovery_mdns.HomeWizardListener") as MockListener:
            listener_instance = MockListener.return_value
            listener_instance.found_ip = None # Never found
            
            start_time = time.time()
            ip = discover_homewizard_p1(timeout=0.1)
            duration = time.time() - start_time
            
            assert ip is None
            # Should have waited at least 0.1s
            assert duration >= 0.1
