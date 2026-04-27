"""Unit tests for configuration management."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.config import ConfigManager
from src.models import Config, ChannelConfig


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary configuration file."""
    config_content = """
channels:
  - channel: "@test_channel"
    destinations:
      - discord_main

discord_webhooks:
  discord_main:
    url: "https://discord.com/api/webhooks/123/abc"

settings:
  max_file_size_mb: 10
  log_level: INFO
  include_channel_name: true
  include_timestamp: true
"""
    config_file = tmp_path / "channels.yaml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def mock_env_vars():
    """Set up mock environment variables."""
    env_vars = {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "test_hash",
        "TELEGRAM_SESSION_NAME": "test_session",
        "LOG_LEVEL": "DEBUG"
    }
    return env_vars


class TestConfigManager:
    """Test configuration manager."""

    def test_init_with_config_path(self, temp_config_file):
        """Test initialization with custom config path."""
        manager = ConfigManager(config_path=temp_config_file)
        assert manager.config_path == temp_config_file

    def test_telegram_api_id(self, mock_env_vars, temp_config_file):
        """Test getting Telegram API ID."""
        with patch.dict(os.environ, mock_env_vars, clear=True):
            manager = ConfigManager(config_path=temp_config_file)
            assert manager.telegram_api_id == 12345

    def test_telegram_api_id_missing(self, temp_config_file):
        """Test missing Telegram API ID."""
        manager = ConfigManager(config_path=temp_config_file)
        with pytest.raises(ValueError, match="TELEGRAM_API_ID environment variable is required"):
            _ = manager.telegram_api_id

    def test_telegram_api_id_invalid(self, temp_config_file):
        """Test invalid Telegram API ID."""
        with patch.dict(os.environ, {"TELEGRAM_API_ID": "invalid", "TELEGRAM_API_HASH": "test"}):
            manager = ConfigManager(config_path=temp_config_file)
            with pytest.raises(ValueError, match="TELEGRAM_API_ID must be a valid integer"):
                _ = manager.telegram_api_id

    def test_telegram_api_hash(self, mock_env_vars, temp_config_file):
        """Test getting Telegram API hash."""
        with patch.dict(os.environ, mock_env_vars, clear=True):
            manager = ConfigManager(config_path=temp_config_file)
            assert manager.telegram_api_hash == "test_hash"

    def test_telegram_api_hash_missing(self, temp_config_file):
        """Test missing Telegram API hash."""
        with patch.dict(os.environ, {"TELEGRAM_API_ID": "12345"}):
            manager = ConfigManager(config_path=temp_config_file)
            with pytest.raises(ValueError, match="TELEGRAM_API_HASH environment variable is required"):
                _ = manager.telegram_api_hash

    def test_telegram_session_name_default(self, temp_config_file):
        """Test default session name."""
        manager = ConfigManager(config_path=temp_config_file)
        assert manager.telegram_session_name == "media_forwarder"

    def test_telegram_session_name_custom(self, mock_env_vars, temp_config_file):
        """Test custom session name."""
        with patch.dict(os.environ, mock_env_vars, clear=True):
            manager = ConfigManager(config_path=temp_config_file)
            assert manager.telegram_session_name == "test_session"

    def test_telegram_session_path(self, temp_config_file):
        """Test session file path."""
        # Mock the DEFAULT_SESSION_DIR to avoid permission errors in CI
        with patch.object(ConfigManager, 'DEFAULT_SESSION_DIR', temp_config_file.parent):
            manager = ConfigManager(config_path=temp_config_file)
            session_path = manager.telegram_session_path
            assert session_path.name == "media_forwarder.session"
            assert "media_forwarder.session" in str(session_path)

    def test_log_level_from_env(self, mock_env_vars, temp_config_file):
        """Test log level from environment variable."""
        with patch.dict(os.environ, mock_env_vars, clear=True):
            manager = ConfigManager(config_path=temp_config_file)
            assert manager.log_level == "DEBUG"

    def test_log_level_default(self, temp_config_file):
        """Test default log level."""
        manager = ConfigManager(config_path=temp_config_file)
        assert manager.log_level == "INFO"

    def test_load_config(self, temp_config_file):
        """Test loading configuration from file."""
        manager = ConfigManager(config_path=temp_config_file)
        config = manager.load()
        
        assert isinstance(config, Config)
        assert len(config.channels) == 1
        assert config.channels[0].channel == "@test_channel"
        assert config.settings.max_file_size_mb == 10

    def test_load_config_file_not_found(self, tmp_path):
        """Test loading non-existent configuration file."""
        manager = ConfigManager(config_path=tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            manager.load()

    def test_load_config_empty_file(self, tmp_path):
        """Test loading empty configuration file."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        manager = ConfigManager(config_path=empty_file)
        with pytest.raises(ValueError, match="Configuration file is empty"):
            manager.load()

    def test_get_webhook_url(self, temp_config_file):
        """Test getting webhook URL by name."""
        manager = ConfigManager(config_path=temp_config_file)
        manager.load()
        url = manager.get_webhook_url("discord_main")
        assert url == "https://discord.com/api/webhooks/123/abc"

    def test_get_webhook_url_not_found(self, temp_config_file):
        """Test getting non-existent webhook."""
        manager = ConfigManager(config_path=temp_config_file)
        manager.load()
        with pytest.raises(ValueError, match="Webhook not found"):
            manager.get_webhook_url("nonexistent")

    def test_get_channels_for_destination(self, temp_config_file):
        """Test getting channels for a specific destination."""
        manager = ConfigManager(config_path=temp_config_file)
        manager.load()
        channels = manager.get_channels_for_destination("discord_main")
        assert len(channels) == 1
        assert channels[0].channel == "@test_channel"

    def test_get_channels_for_destination_none(self, temp_config_file):
        """Test getting channels for non-existent destination."""
        manager = ConfigManager(config_path=temp_config_file)
        manager.load()
        channels = manager.get_channels_for_destination("nonexistent")
        assert len(channels) == 0

    def test_config_lazy_loading(self, temp_config_file):
        """Test lazy loading of configuration."""
        manager = ConfigManager(config_path=temp_config_file)
        assert manager._config is None
        
        # Access config property should load it
        config = manager.config
        assert config is not None
        assert manager._config is not None
        
        # Subsequent accesses should use cached config
        config2 = manager.config
        assert config is config2
