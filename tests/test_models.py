"""Unit tests for data models."""

import pytest
from pydantic import ValidationError
from src.models import DiscordWebhook, ChannelConfig, Settings, Config


class TestDiscordWebhook:

    def test_valid_webhook_url(self):
        webhook = DiscordWebhook(url="https://discord.com/api/webhooks/123/abc")
        assert webhook.url == "https://discord.com/api/webhooks/123/abc"

    def test_valid_ptb_webhook_url(self):
        webhook = DiscordWebhook(url="https://ptb.discord.com/api/webhooks/123/abc")
        assert webhook.url == "https://ptb.discord.com/api/webhooks/123/abc"

    def test_invalid_webhook_url(self):
        with pytest.raises(ValidationError, match="Invalid Discord webhook URL"):
            DiscordWebhook(url="https://example.com/webhook")

    def test_webhook_with_name(self):
        webhook = DiscordWebhook(
            url="https://discord.com/api/webhooks/123/abc",
            name="test_webhook"
        )
        assert webhook.name == "test_webhook"

    def test_webhook_max_file_size_zero(self):
        with pytest.raises(ValidationError, match="Max file size must be between"):
            DiscordWebhook(url="https://discord.com/api/webhooks/123/abc", max_file_size_mb=0)

    def test_webhook_max_file_size_over_500(self):
        with pytest.raises(ValidationError, match="Max file size must be between"):
            DiscordWebhook(url="https://discord.com/api/webhooks/123/abc", max_file_size_mb=501)

    def test_webhook_max_file_size_valid(self):
        webhook = DiscordWebhook(url="https://discord.com/api/webhooks/123/abc", max_file_size_mb=250)
        assert webhook.max_file_size_mb == 250

    def test_webhook_no_max_file_size(self):
        webhook = DiscordWebhook(url="https://discord.com/api/webhooks/123/abc")
        assert webhook.max_file_size_mb is None


class TestChannelConfig:

    def test_channel_with_username(self):
        config = ChannelConfig(channel="@test_channel", destinations=["discord_main"])
        assert config.channel == "@test_channel"

    def test_channel_with_numeric_id(self):
        config = ChannelConfig(channel="-1001234567890", destinations=["discord_main"])
        assert config.channel == "-1001234567890"

    def test_channel_with_integer_id(self):
        config = ChannelConfig(channel=-1001234567890, destinations=["discord_main"])
        assert config.channel == "-1001234567890"

    def test_invalid_username_too_short(self):
        with pytest.raises(ValidationError, match="Invalid channel username"):
            ChannelConfig(channel="@abc", destinations=["discord_main"])

    def test_invalid_username_too_long(self):
        with pytest.raises(ValidationError, match="Invalid channel username"):
            ChannelConfig(channel="@" + "a" * 33, destinations=["discord_main"])

    def test_invalid_channel_format(self):
        with pytest.raises(ValidationError, match="Invalid channel ID"):
            ChannelConfig(channel="invalid_format", destinations=["discord_main"])

    def test_channel_with_float_raises(self):
        with pytest.raises(ValidationError, match="Channel must be a string or integer"):
            ChannelConfig(channel=3.14, destinations=["discord_main"])

    def test_channel_with_list_raises(self):
        with pytest.raises(ValidationError, match="Channel must be a string or integer"):
            ChannelConfig(channel=["@test"], destinations=["discord_main"])

    def test_multiple_destinations(self):
        config = ChannelConfig(channel="@test_channel", destinations=["discord_main", "discord_backup"])
        assert len(config.destinations) == 2

    def test_channel_no_settings(self):
        config = ChannelConfig(channel="@test_channel", destinations=["discord_main"])
        assert config.settings is None


class TestSettings:

    def test_default_settings(self):
        settings = Settings()
        assert settings.max_file_size_mb == 10
        assert settings.log_level == "INFO"
        assert settings.include_channel_name is True
        assert settings.include_timestamp is True

    def test_custom_settings(self):
        settings = Settings(
            max_file_size_mb=25,
            log_level="DEBUG",
            include_channel_name=False,
            include_timestamp=False
        )
        assert settings.max_file_size_mb == 25
        assert settings.log_level == "DEBUG"

    def test_invalid_log_level(self):
        with pytest.raises(ValidationError, match="Log level must be one of"):
            Settings(log_level="INVALID")

    def test_max_file_size_too_small(self):
        with pytest.raises(ValidationError, match="Max file size must be between"):
            Settings(max_file_size_mb=0)

    def test_max_file_size_too_large(self):
        with pytest.raises(ValidationError, match="Max file size must be between"):
            Settings(max_file_size_mb=501)

    def test_log_level_uppercase_conversion(self):
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

    def test_max_file_size_boundary_1(self):
        settings = Settings(max_file_size_mb=1)
        assert settings.max_file_size_mb == 1

    def test_max_file_size_boundary_500(self):
        settings = Settings(max_file_size_mb=500)
        assert settings.max_file_size_mb == 500


class TestConfig:

    def test_minimal_config(self):
        config = Config(
            channels=[ChannelConfig(channel="@test_channel", destinations=["discord_main"])],
            discord_webhooks={"discord_main": {"url": "https://discord.com/api/webhooks/123/abc"}}
        )
        assert len(config.channels) == 1

    def test_missing_webhook_destination(self):
        with pytest.raises(ValidationError, match="Missing webhook configurations"):
            Config(
                channels=[ChannelConfig(channel="@test_channel", destinations=["missing_webhook"])],
                discord_webhooks={}
            )

    def test_multiple_channels(self):
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
        config = Config(
            channels=[
                ChannelConfig(channel="@channel1", destinations=["shared"]),
                ChannelConfig(channel="@channel2", destinations=["shared"]),
            ],
            discord_webhooks={"shared": {"url": "https://discord.com/api/webhooks/123/abc"}}
        )
        assert len(config.channels) == 2
        assert len(config.discord_webhooks) == 1

    def test_config_with_webhook_objects(self):
        config = Config(
            channels=[ChannelConfig(channel="@test_channel", destinations=["main"])],
            discord_webhooks={
                "main": DiscordWebhook(url="https://discord.com/api/webhooks/123/abc", max_file_size_mb=25)
            }
        )
        assert config.discord_webhooks["main"].max_file_size_mb == 25

    def test_config_default_settings(self):
        config = Config(
            channels=[ChannelConfig(channel="@test_channel", destinations=["main"])],
            discord_webhooks={"main": {"url": "https://discord.com/api/webhooks/123/abc"}}
        )
        assert config.settings.max_file_size_mb == 10
        assert config.settings.log_level == "INFO"

    def test_empty_channels_list(self):
        config = Config(
            channels=[],
            discord_webhooks={}
        )
        assert len(config.channels) == 0
