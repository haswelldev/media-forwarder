"""Data models for media-forwarder."""

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator
import re


class DiscordWebhook(BaseModel):
    """Discord webhook configuration."""
    url: str = Field(..., description="Discord webhook URL")
    name: Optional[str] = None
    max_file_size_mb: Optional[int] = Field(None, description="Override max file size for this destination")

    @field_validator('url')
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        if not v.startswith('https://discord.com/api/webhooks/') and not v.startswith('https://ptb.discord.com/api/webhooks/'):
            raise ValueError('Invalid Discord webhook URL')
        return v

    @field_validator('max_file_size_mb')
    @classmethod
    def validate_max_file_size(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v <= 0 or v > 500):
            raise ValueError('Max file size must be between 1 and 500 MB')
        return v


class ChannelSettings(BaseModel):
    """Per-channel settings."""
    media_only: bool = Field(False, description="Only forward messages with media, skip text-only posts")
    remove_captions: bool = Field(False, description="Remove captions from media posts")
    translate_captions: bool = Field(False, description="Translate captions to English")
    max_file_size_mb: Optional[int] = Field(None, description="Override max file size for this channel")
    include_channel_name: Optional[bool] = Field(None, description="Override include channel name")
    include_timestamp: Optional[bool] = Field(None, description="Override include timestamp")


class ChannelConfig(BaseModel):
    """Channel monitoring configuration."""
    channel: str = Field(..., description="Channel username or ID (e.g., @channel_name or -1001234567890)")
    destinations: List[str] = Field(..., description="List of destination names")
    settings: Optional[ChannelSettings] = Field(None, description="Channel-specific settings")

    @field_validator('channel', mode='before')
    @classmethod
    def validate_channel(cls, v):
        # Convert integer to string if needed
        if isinstance(v, int):
            v = str(v)
        
        if not isinstance(v, str):
            raise ValueError(f'Channel must be a string or integer, got {type(v).__name__}')
        
        if v.startswith('@'):
            if not re.match(r'^@[a-zA-Z0-9_]{5,32}$', v):
                raise ValueError(f'Invalid channel username: {v}')
        else:
            # Validate it's a valid numeric ID (can be positive or negative)
            if not v.lstrip('-').isdigit():
                raise ValueError(f'Invalid channel ID: {v}')
        
        return v


class Settings(BaseModel):
    """Default application settings."""
    max_file_size_mb: int = Field(10, description="Maximum file size in MB to upload to Discord")
    log_level: str = Field("INFO", description="Logging level")
    include_channel_name: bool = Field(True, description="Include channel name in forwarded message")
    include_timestamp: bool = Field(True, description="Include timestamp in forwarded message")
    group_timeout_seconds: float = Field(3.0, description="Seconds to wait for album messages to arrive before forwarding")

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {", ".join(valid_levels)}')
        return v.upper()

    @field_validator('max_file_size_mb')
    @classmethod
    def validate_max_file_size(cls, v: int) -> int:
        if v <= 0 or v > 500:
            raise ValueError('Max file size must be between 1 and 500 MB')
        return v


class Config(BaseModel):
    """Main configuration model."""
    channels: List[ChannelConfig]
    discord_webhooks: dict = Field(default_factory=dict)
    settings: Settings = Field(default_factory=Settings)

    @field_validator('discord_webhooks')
    @classmethod
    def validate_webhooks(cls, v: dict, info) -> dict:
        if 'channels' in info.data:
            destinations = set()
            for channel in info.data['channels']:
                destinations.update(channel.destinations)
            
            missing = destinations - set(v.keys())
            if missing:
                raise ValueError(f'Missing webhook configurations for: {", ".join(missing)}')
        
        return v
