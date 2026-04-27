"""Main forwarding logic."""

import logging
from datetime import datetime
from telethon.tl.types import Message, Channel
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from .config import ConfigManager
from .telegram_client import TelegramMonitor
from .discord_client import DiscordSender

logger = logging.getLogger(__name__)


class MediaForwarder:
    """Forward media from Telegram to Discord."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize media forwarder."""
        self.config = config_manager
        self.telegram = TelegramMonitor(config_manager)

    async def initialize(self):
        """Initialize forwarder."""
        await self.telegram.initialize()
        self.telegram.set_message_callback(self.handle_message)

    async def handle_message(self, message: Message, chat: Channel):
        """Handle incoming Telegram message."""
        # Find channel configuration
        channel_config = self._get_channel_config(chat)
        if not channel_config:
            logger.warning(f'No configuration found for channel: {chat.username or chat.id}')
            return

        # Extract message content
        text = message.text or message.message
        media_data = None
        media_type = None
        filename = 'file'

        # Handle photo
        if message.photo:
            media_data = await self.telegram.download_media(message)
            media_type = 'photo'
            filename = f'photo_{message.id}.jpg'

        # Handle video
        elif message.video:
            media_data = await self.telegram.download_media(message)
            media_type = 'video'
            if message.video.attributes:
                for attr in message.video.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        filename = attr.file_name
                        break
            if filename == 'file':
                filename = f'video_{message.id}.mp4'

        # Handle document
        elif message.document:
            media_data = await self.telegram.download_media(message)
            media_type = 'document'
            if message.document.attributes:
                for attr in message.document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        filename = attr.file_name
                        break
            if filename == 'file':
                filename = f'document_{message.id}'

        # Format message text
        formatted_text = self._format_message(text, chat, message)

        # Forward to each destination
        for destination_name in channel_config.destinations:
            try:
                webhook_url = self.config.get_webhook_url(destination_name)
                sender = DiscordSender(
                    webhook_url,
                    self.config.config.settings.max_file_size_mb
                )

                # Send based on media type
                if media_type == 'photo' and media_data:
                    success = await sender.send_photo(formatted_text, media_data)
                elif media_type == 'video' and media_data:
                    success = await sender.send_video(formatted_text, media_data, filename)
                elif media_type == 'document' and media_data:
                    success = await sender.send_document(formatted_text, media_data, filename)
                else:
                    success = await sender.send_message(formatted_text)

                if success:
                    logger.info(
                        f'Forwarded message {message.id} from {chat.username or chat.id} '
                        f'to {destination_name}'
                    )
                else:
                    logger.warning(
                        f'Failed to forward message {message.id} to {destination_name}'
                    )

            except Exception as e:
                logger.error(
                    f'Error forwarding to {destination_name}: {e}',
                    exc_info=True
                )

    def _get_channel_config(self, chat: Channel):
        """Get channel configuration for a chat."""
        channel_identifier = f'@{chat.username}' if chat.username else str(chat.id)
        
        for channel_config in self.config.config.channels:
            if channel_config.channel == channel_identifier:
                return channel_config
        
        return None

    def _format_message(self, text: str, chat: Channel, message: Message) -> str:
        """Format message for Discord."""
        parts = []

        # Add channel name if enabled
        if self.config.config.settings.include_channel_name:
            channel_name = chat.title or chat.username or str(chat.id)
            parts.append(f'**From:** {channel_name}')

        # Add timestamp if enabled
        if self.config.config.settings.include_timestamp:
            timestamp = datetime.fromtimestamp(message.date).strftime('%Y-%m-%d %H:%M:%S')
            parts.append(f'**Time:** {timestamp}')

        # Add message text
        if text:
            if parts:
                parts.append('---')
            parts.append(text)

        return '\n'.join(parts) if parts else ''

    async def run(self):
        """Run the forwarder."""
        logger.info('Starting media forwarder')
        await self.telegram.run()

    async def stop(self):
        """Stop the forwarder."""
        logger.info('Stopping media forwarder')
        await self.telegram.disconnect()
