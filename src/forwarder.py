"""Main forwarding logic."""

import logging
from datetime import datetime
from telethon.tl.types import Channel, Message, MessageMediaPhoto
from deep_translator import GoogleTranslator
from src.config import ConfigManager
from src.telegram_client import TelegramMonitor
from src.discord_client import DiscordSender

logger = logging.getLogger(__name__)


class MediaForwarder:
    """Forward media from Telegram to Discord."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize media forwarder."""
        self.config = config_manager
        self.telegram = TelegramMonitor(config_manager)
        self.translator = GoogleTranslator(source='auto', target='en')

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

        # Get channel-specific settings (if any)
        channel_settings = channel_config.settings

        # Extract message content
        text = message.text or message.message
        media_data = None
        media_type = None
        filename = 'file'
        has_media = False

        # Handle photo
        if message.photo:
            media_data = await self.telegram.download_media(message)
            media_type = 'photo'
            filename = f'photo_{message.id}.jpg'
            has_media = True

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
            has_media = True

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
            has_media = True

        # Check media-only filter
        if channel_settings and channel_settings.media_only and not has_media:
            logger.debug(f'Skipping text-only message {message.id} (media_only=True)')
            return

        # Remove captions if configured
        if channel_settings and channel_settings.remove_captions and has_media:
            text = None
            logger.debug(f'Removed caption from message {message.id}')

        # Translate captions if configured
        if text and channel_settings and channel_settings.translate_captions:
            text = await self._translate_text(text)
            if text:
                logger.debug(f'Translated caption for message {message.id}')

        # Format message text
        formatted_text = self._format_message(text, chat, message, channel_settings)

        # Determine max file size
        if channel_settings and channel_settings.max_file_size_mb:
            max_file_size = channel_settings.max_file_size_mb
        else:
            max_file_size = self.config.config.settings.max_file_size_mb

        # Forward to each destination
        for destination_name in channel_config.destinations:
            try:
                webhook_url = self.config.get_webhook_url(destination_name)
                sender = DiscordSender(
                    webhook_url,
                    max_file_size
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

    async def _translate_text(self, text: str) -> str:
        """Translate text to English."""
        try:
            translated = self.translator.translate(text)
            return translated
        except Exception as e:
            logger.warning(f'Translation failed: {e}')
            return text  # Return original text if translation fails

    def _get_channel_config(self, chat: Channel):
        """Get channel configuration for a chat."""
        channel_identifier = f'@{chat.username}' if chat.username else str(chat.id)
        
        for channel_config in self.config.config.channels:
            if channel_config.channel == channel_identifier:
                return channel_config
        
        return None

    def _format_message(self, text: str, chat: Channel, message: Message, channel_settings=None) -> str:
        """Format message for Discord."""
        parts = []

        # Determine settings
        include_channel_name = self.config.config.settings.include_channel_name
        include_timestamp = self.config.config.settings.include_timestamp
        
        if channel_settings:
            if channel_settings.include_channel_name is not None:
                include_channel_name = channel_settings.include_channel_name
            if channel_settings.include_timestamp is not None:
                include_timestamp = channel_settings.include_timestamp

        # Add channel name if enabled
        if include_channel_name:
            channel_name = chat.title or chat.username or str(chat.id)
            parts.append(f'**From:** {channel_name}')

        # Add timestamp if enabled
        if include_timestamp:
            timestamp = message.date.strftime('%Y-%m-%d %H:%M:%S')
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
