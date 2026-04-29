"""Configuration loader for media-forwarder."""

import os
import yaml
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv
from .models import Config, Settings, ChannelConfig, DiscordWebhook

# Load environment variables
load_dotenv()


class ConfigManager:
    """Manage application configuration."""

    DEFAULT_CONFIG_PATH = Path('/app/config/channels.yaml')
    DEFAULT_SESSION_DIR = Path('/app/sessions')

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager."""
        env_config = os.getenv('CONFIG_PATH')
        self.config_path = config_path or (Path(env_config) if env_config else self.DEFAULT_CONFIG_PATH)
        self._config: Optional[Config] = None

    @property
    def telegram_api_id(self) -> int:
        """Get Telegram API ID from environment."""
        api_id = os.getenv('TELEGRAM_API_ID')
        if not api_id:
            raise ValueError('TELEGRAM_API_ID environment variable is required')
        try:
            return int(api_id)
        except ValueError:
            raise ValueError('TELEGRAM_API_ID must be a valid integer')

    @property
    def telegram_api_hash(self) -> str:
        """Get Telegram API hash from environment."""
        api_hash = os.getenv('TELEGRAM_API_HASH')
        if not api_hash:
            raise ValueError('TELEGRAM_API_HASH environment variable is required')
        return api_hash

    @property
    def telegram_session_name(self) -> str:
        """Get Telegram session name from environment."""
        return os.getenv('TELEGRAM_SESSION_NAME', 'media_forwarder')

    @property
    def _session_dir(self) -> Path:
        """Get session directory, respecting SESSION_DIR env var."""
        env_dir = os.getenv('SESSION_DIR')
        return Path(env_dir) if env_dir else self.DEFAULT_SESSION_DIR

    @property
    def telegram_session_path(self) -> Path:
        """Get full path to Telegram session file."""
        session_dir = self._session_dir
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / f'{self.telegram_session_name}.session'

    @property
    def log_level(self) -> str:
        """Get log level from environment or config."""
        return os.getenv('LOG_LEVEL', 'INFO').upper()

    def load(self) -> Config:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f'Configuration file not found: {self.config_path}\n'
                f'Please create a configuration file with your channels and webhooks.'
            )

        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError('Configuration file is empty')

        # Override settings with environment variables if provided
        if 'settings' in data:
            if os.getenv('LOG_LEVEL'):
                data['settings']['log_level'] = self.log_level

        self._config = Config(**data)
        return self._config

    @property
    def config(self) -> Config:
        """Get configuration (lazy load)."""
        if self._config is None:
            self.load()
        return self._config

    def get_webhook_url(self, name: str) -> str:
        """Get webhook URL by name."""
        webhook_config = self.config.discord_webhooks.get(name)
        if not webhook_config:
            raise ValueError(f'Webhook not found: {name}')
        
        if isinstance(webhook_config, dict):
            return webhook_config['url']
        return webhook_config

    def get_channels_for_destination(self, destination: str) -> list[ChannelConfig]:
        """Get all channels that forward to a specific destination."""
        return [
            channel for channel in self.config.channels
            if destination in channel.destinations
        ]
