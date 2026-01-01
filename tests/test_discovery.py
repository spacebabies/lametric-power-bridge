import pytest
from sources.discovery import discover_homewizard, discover_lametric


@pytest.mark.asyncio
async def test_discover_homewizard_found(mocker):
    """Test successful HomeWizard discovery"""
    # Mock service info
    mock_service_info = mocker.Mock()
    mock_service_info.parsed_addresses.return_value = ["192.168.1.87"]

    # Mock zeroconf
    mock_zeroconf = mocker.Mock()
    mock_zeroconf.async_get_service_info = mocker.AsyncMock(return_value=mock_service_info)

    # Mock AsyncZeroconf context manager
    mock_azc = mocker.AsyncMock()
    mock_azc.__aenter__.return_value.zeroconf = mock_zeroconf
    mock_azc.__aexit__.return_value = None

    mocker.patch('sources.discovery.AsyncZeroconf', return_value=mock_azc)

    # Mock ServiceBrowser to immediately trigger discovery
    mock_browser = mocker.Mock()
    mock_browser.cancel = mocker.Mock()

    def create_browser(zc, service_type, listener):
        # Simulate service found immediately
        listener.add_service(zc, service_type, "homewizard-abc123._hwenergy._tcp.local.")
        return mock_browser

    mocker.patch('sources.discovery.ServiceBrowser', side_effect=create_browser)

    # Run discovery
    ip = await discover_homewizard(timeout=1.0)

    assert ip == "192.168.1.87"
    mock_browser.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_discover_homewizard_timeout(mocker):
    """Test HomeWizard discovery timeout"""
    # Mock AsyncZeroconf context manager (no services found)
    mock_azc = mocker.AsyncMock()
    mock_azc.__aenter__.return_value.zeroconf = mocker.Mock()
    mock_azc.__aexit__.return_value = None

    mocker.patch('sources.discovery.AsyncZeroconf', return_value=mock_azc)

    # Mock ServiceBrowser (doesn't trigger any discovery)
    mock_browser = mocker.Mock()
    mock_browser.cancel = mocker.Mock()
    mocker.patch('sources.discovery.ServiceBrowser', return_value=mock_browser)

    # Run discovery with short timeout
    ip = await discover_homewizard(timeout=0.1)

    assert ip is None
    mock_browser.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_discover_homewizard_library_not_installed(mocker):
    """Test HomeWizard discovery when zeroconf not installed"""
    # Mock missing library
    mocker.patch('sources.discovery.AsyncZeroconf', None)
    mocker.patch('sources.discovery.ServiceBrowser', None)
    mocker.patch('sources.discovery.ServiceListener', None)

    # Run discovery
    ip = await discover_homewizard(timeout=1.0)

    assert ip is None


@pytest.mark.asyncio
async def test_discover_lametric_found(mocker):
    """Test successful LaMetric discovery"""
    # Mock SSDP search results
    async def mock_search(timeout, search_target):
        yield {"location": "http://192.168.1.50:4343/description.xml"}

    mocker.patch('sources.discovery.async_search', new=mock_search)

    # Run discovery
    ip = await discover_lametric(timeout=1.0)

    assert ip == "192.168.1.50"


@pytest.mark.asyncio
async def test_discover_lametric_timeout(mocker):
    """Test LaMetric discovery timeout"""
    # Mock SSDP search with no results
    async def mock_search(timeout, search_target):
        # Empty generator - yields nothing
        if False:
            yield

    mocker.patch('sources.discovery.async_search', new=mock_search)

    # Run discovery
    ip = await discover_lametric(timeout=0.1)

    assert ip is None


@pytest.mark.asyncio
async def test_discover_lametric_library_not_installed(mocker):
    """Test LaMetric discovery when async-upnp-client not installed"""
    # Mock missing library
    mocker.patch('sources.discovery.async_search', None)

    # Run discovery
    ip = await discover_lametric(timeout=1.0)

    assert ip is None


@pytest.mark.asyncio
async def test_discover_lametric_invalid_location(mocker):
    """Test LaMetric discovery with invalid location URL"""
    # Mock SSDP search with malformed location
    async def mock_search(timeout, search_target):
        yield {"location": "invalid-url"}

    mocker.patch('sources.discovery.async_search', new=mock_search)

    # Run discovery
    ip = await discover_lametric(timeout=1.0)

    # Should return None for invalid URL (hostname extraction fails)
    assert ip is None
