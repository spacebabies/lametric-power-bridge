"""Integration tests for environment variable precedence"""
import os
import subprocess
import sys
import pytest

@pytest.mark.skipif(sys.platform == "win32", reason="Shell tests are easier on Unix")
def test_env_var_precedence_over_file(tmp_path):
    """
    Verify that actual environment variables take precedence over .env file values.
    """
    # Create a dummy .env file in the temp dir
    env_file = tmp_path / "lametric-power-bridge.env"
    env_file.write_text("TIBBER_TOKEN=from_file_value\n")
    
    # Prepare environment for the subprocess
    env = os.environ.copy()
    env["TIBBER_TOKEN"] = "from_env_value"
    env["PYTHONPATH"] = os.getcwd() # Ensure we can from lametric_power_bridge import main as bridge
    
    # Run a snippet that imports bridge and checks the token
    # We run inside tmp_path so bridge.py looks for .env there
    cmd = [
        sys.executable, 
        "-c", 
        "from lametric_power_bridge.main import get_source; print(get_source('tibber').token)"
    ]
    
    result = subprocess.run(
        cmd,
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=True
    )
    
    # The output should contain the value from the environment, not the file
    assert "from_env_value" in result.stdout
    assert "from_file_value" not in result.stdout

@pytest.mark.skipif(sys.platform == "win32", reason="Shell tests are easier on Unix")
def test_missing_env_file_works(tmp_path):
    """
    Verify that the application works even if .env file is completely missing,
    provided the necessary environment variables are set.
    """
    # Ensure NO .env file exists in tmp_path
    
    # Prepare environment
    env = os.environ.copy()
    env["TIBBER_TOKEN"] = "only_in_env_value"
    env["PYTHONPATH"] = os.getcwd()
    
    cmd = [
        sys.executable, 
        "-c", 
        "from lametric_power_bridge.main import get_source; print(get_source('tibber').token)"
    ]
    
    result = subprocess.run(
        cmd,
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=True
    )
    
    assert "only_in_env_value" in result.stdout
