"""Data models for media-forwarder."""

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, validator
import re


class DiscordWebhook(BaseModel):
    """Discord webhook configuration."""
    url: str = Field(..., description="Discord webhook URL")
    name: Optional[str] = None

    @validator('url')
    def validate_webhook_url(cls, v):
        if not v.startswith('https://discord.com/api/webhooks/') and not v.startswith('https://ptb.discord.com/api/webhooks/'):
            raise ValueError('Invalid Discord webhook URL')
        return v


class ChannelConfig(BaseModel):
    """Channel monitoring configuration."""
    channel: str = Field(..., description="Channel username or ID (e.g., @channel_name or -1001234567890)")
    destinations: List[str] = Field(..., description="List of destination names")

    @validator('channel')
    def validate_channel(cls, v):
        if v.startswith('@'):
            if not re.match(r'^@[a-zA-Z0-9_]{5,32}$', v):
                raise ValueError(f'Invalid channel username: {v}')
        else:
            try:
                int(v)
            except ValueError:
                raise ValueError(f'Invalid channel ID: {v}')
        return v


class Settings(BaseModel):
    """Application settings."""
    max_file_size_mb: int = Field(10, description="Maximum file size in MB to upload to Discord")
    log_level: str = Field("INFO", description="Logging level")
    include_channel_name: bool = Field(True, description="Include channel name in forwarded message")
    include_timestamp: bool = Field(True, description="Include timestamp in forwarded message")

    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {", ".join(valid_levels)}')
        return v.upper()

    @validator('max_file_size_mb')
    def validate_max_file_size(cls, v):
        if v <= 0 or v > 500:
            raise ValueError('Max file size must be between 1 and 500 MB')
        return v


class Config(BaseModel):
    """Main configuration model."""
    channels: List[ChannelConfig]
    discord_webhooks: dict = Field(default_factory=dict)
    settings: Settings = Field(default_factory=Settings)

    @validator('discord_webhooks')
    def validate_webhooks(cls, v, values):
        destinations = set()
        for channel in values.get('channels', []):
            destinations.update(channel.destinations)
        
        missing = destinations - set(v.keys())
        if missing:
            raise ValueError(f'Missing webhook configurations for: {", ".join(missing)}')
        
        return v
