from pytest_socket import disable_socket

def pytest_runtest_setup():
    """
    Runs before every test.
    We disable network access. Every attempt to connect
    (HTTP, DNS, etc) will immediately raise a SocketBlockedError.
    """
    disable_socket(allow_unix_socket=True)