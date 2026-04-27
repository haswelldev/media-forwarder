"""Unit tests for data models."""

import pytest
from pydantic import ValidationError
from src.models import DiscordWebhook, ChannelConfig, Settings, Config


class TestDiscordWebhook:
    """Test Discord webhook model."""

    def test_valid_webhook_url(self):
        """Test valid Discord webhook URL."""
        webhook = DiscordWebhook(url="https://discord.com/api/webhooks/123/abc")
        assert webhook.url == "https://discord.com/api/webhooks/123/abc"

    def test_valid_ptb_webhook_url(self):
        """Test valid PTB Discord webhook URL."""
        webhook = DiscordWebhook(url="https://ptb.discord.com/api/webhooks/123/abc")
        assert webhook.url == "https://ptb.discord.com/api/webhooks/123/abc"

    def test_invalid_webhook_url(self):
        """Test invalid Discord webhook URL."""
        with pytest.raises(ValidationError, match="Invalid Discord webhook URL"):
            DiscordWebhook(url="https://example.com/webhook")

    def test_webhook_with_name(self):
        """Test webhook with optional name."""
        webhook = DiscordWebhook(
            url="https://discord.com/api/webhooks/123/abc",
            name="test_webhook"
        )
        assert webhook.name == "test_webhook"


class TestChannelConfig:
    """Test channel configuration model."""

    def test_channel_with_username(self):
        """Test channel configuration with username."""
        config = ChannelConfig(
            channel="@test_channel",
            destinations=["discord_main"]
        )
        assert config.channel == "@test_channel"
        assert config.destinations == ["discord_main"]

    def test_channel_with_numeric_id(self):
        """Test channel configuration with numeric ID."""
        config = ChannelConfig(
            channel="-1001234567890",
            destinations=["discord_main"]
        )
        assert config.channel == "-1001234567890"

    def test_channel_with_integer_id(self):
        """Test channel configuration with integer ID (YAML parsing)."""
        config = ChannelConfig(
            channel=-1001234567890,  # Integer (as YAML would parse it)
            destinations=["discord_main"]
        )
        assert config.channel == "-1001234567890"  # Should be converted to string

    def test_invalid_username_too_short(self):
        """Test invalid username (too short)."""
        with pytest.raises(ValidationError, match="Invalid channel username"):
            ChannelConfig(
                channel="@abc",
                destinations=["discord_main"]
            )

    def test_invalid_username_too_long(self):
        """Test invalid username (too long)."""
        with pytest.raises(ValidationError, match="Invalid channel username"):
            ChannelConfig(
                channel="@a" * 33,
                destinations=["discord_main"]
            )

    def test_invalid_channel_format(self):
        """Test invalid channel format."""
        with pytest.raises(ValidationError, match="Invalid channel ID"):
            ChannelConfig(
                channel="invalid_format",
                destinations=["discord_main"]
            )

    def test_multiple_destinations(self):
        """Test channel with multiple destinations."""
        config = ChannelConfig(
            channel="@test_channel",
            destinations=["discord_main", "discord_backup"]
        )
        assert len(config.destinations) == 2


class TestSettings:
    """Test application settings model."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.max_file_size_mb == 10
        assert settings.log_level == "INFO"
        assert settings.include_channel_name is True
        assert settings.include_timestamp is True

    def test_custom_settings(self):
        """Test custom settings."""
        settings = Settings(
            max_file_size_mb=25,
            log_level="DEBUG",
            include_channel_name=False,
            include_timestamp=False
        )
        assert settings.max_file_size_mb == 25
        assert settings.log_level == "DEBUG"
        assert settings.include_channel_name is False
        assert settings.include_timestamp is False

    def test_invalid_log_level(self):
        """Test invalid log level."""
        with pytest.raises(ValidationError, match="Log level must be one of"):
            Settings(log_level="INVALID")

    def test_max_file_size_too_small(self):
        """Test max file size too small."""
        with pytest.raises(ValidationError, match="Max file size must be between"):
            Settings(max_file_size_mb=0)

    def test_max_file_size_too_large(self):
        """Test max file size too large."""
        with pytest.raises(ValidationError, match="Max file size must be between"):
            Settings(max_file_size_mb=501)

    def test_log_level_uppercase_conversion(self):
        """Test log level is converted to uppercase."""
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"


class TestConfig:
    """Test main configuration model."""

    def test_minimal_config(self):
        """Test minimal valid configuration."""
        config = Config(
            channels=[
                ChannelConfig(
                    channel="@test_channel",
                    destinations=["discord_main"]
                )
            ],
            discord_webhooks={
                "discord_main": {
                    "url": "https://discord.com/api/webhooks/123/abc"
                }
            }
        )
        assert len(config.channels) == 1
        assert len(config.discord_webhooks) == 1

    def test_missing_webhook_destination(self):
        """Test configuration with missing webhook destination."""
        with pytest.raises(ValidationError, match="Missing webhook configurations"):
            Config(
                channels=[
                    ChannelConfig(
                        channel="@test_channel",
                        destinations=["missing_webhook"]
                    )
                ],
                discord_webhooks={}
            )

    def test_multiple_channels(self):
        """Test configuration with multiple channels."""
        config = Config(
            channels=[
                ChannelConfig(channel="@channel1", destinations=["webhook1"]),
                ChannelConfig(channel="@channel2", destinations=["webhook2"]),
            ],
            discord_webhooks={
                "webhook1": {"url": "https://discord.com/api/webhooks/1/a"},
                "webhook2": {"url": "https://discord.com/api/webhooks/2/b"},
            }
        )
        assert len(config.channels) == 2

    def test_shared_destination(self):
        """Test multiple channels sharing same destination."""
        config = Config(
            channels=[
                ChannelConfig(channel="@channel1", destinations=["shared"]),
                ChannelConfig(channel="@channel2", destinations=["shared"]),
            ],
            discord_webhooks={
                "shared": {"url": "https://discord.com/api/webhooks/123/abc"}
            }
        )
        assert len(config.channels) == 2
        assert len(config.discord_webhooks) == 1
