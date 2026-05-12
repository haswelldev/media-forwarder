"""Telegram client for monitoring channels."""

import asyncio
import logging
import os
import tempfile
from typing import Optional, Union
from telethon import TelegramClient, events
from telethon.tl.types import Channel, MessageMediaPhoto, MessageMediaDocument
from .config import ConfigManager

_CONNECT_TIMEOUT = 30
_ENTITY_TIMEOUT = 15
_IN_MEMORY_LIMIT = 50 * 1024 * 1024

logger = logging.getLogger(__name__)


class TelegramMonitor:
    """Monitor Telegram channels for new posts."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize Telegram monitor."""
        self.config = config_manager
        self.client: Optional[TelegramClient] = None
        self.message_callback = None

    async def initialize(self):
        """Initialize Telegram client."""
        try:
            self.client = TelegramClient(
                str(self.config.telegram_session_path),
                self.config.telegram_api_id,
                self.config.telegram_api_hash
            )
            
            # Connect to Telegram (with timeout so a network hang doesn't stall the container)
            await asyncio.wait_for(self.client.connect(), timeout=_CONNECT_TIMEOUT)

            # Check if session is authorized
            if not await self.client.is_user_authorized():
                raise Exception(
                    'Session is not authorized. Please run: python -m src.main login'
                )
            
            logger.info('Telegram client initialized successfully')
            
        except Exception as e:
            logger.error(f'Failed to initialize Telegram client: {e}')
            raise

    def set_message_callback(self, callback):
        """Set callback for new messages."""
        self.message_callback = callback

    async def start_monitoring(self):
        """Start monitoring configured channels."""
        if not self.client:
            raise Exception('Telegram client not initialized')
        
        # Get list of channel IDs/username to monitor
        channels_to_monitor = []
        inaccessible_channels = []
        
        for channel_config in self.config.config.channels:
            try:
                # Convert channel identifier to proper format
                channel_id = channel_config.channel
                if channel_id.lstrip('-').isdigit():
                    channel_id = int(channel_id)

                # Fetch the full entity to ensure it's in Telethon's cache.
                # Channel IDs in config should be @username or the full -100XXXXXXXXXX form.
                # Bare positive integers are user IDs, not channel IDs, and will fail here.
                await asyncio.wait_for(self.client.get_entity(channel_id), timeout=_ENTITY_TIMEOUT)

                # Use the channel_id directly for event filtering.
                # Telethon's event.chat_id returns the full ID (with -100 prefix)
                # for channels, so we need to match that format.
                channels_to_monitor.append(channel_id)

                logger.info(f'Added channel to monitoring: {channel_config.channel}')
            except Exception as e:
                logger.warning(
                    f'Cannot access channel {channel_config.channel}: {e}. '
                    f'Skipping this channel.'
                )
                inaccessible_channels.append(channel_config.channel)
        
        if not channels_to_monitor:
            logger.error('No accessible channels to monitor!')
            return
        
        if inaccessible_channels:
            logger.warning(
                f'Inaccessible channels (skipped): {", ".join(inaccessible_channels)}'
            )
        
        logger.info(f'Successfully monitoring: {", ".join(str(c) for c in channels_to_monitor)}')
        
        # Store channels for checking forwarded messages
        self.monitored_channel_ids = set(channels_to_monitor)

        # Set up event handler for new messages in monitored channels
        @self.client.on(events.NewMessage(chats=channels_to_monitor))
        async def handle_channel_message(event):
            """Handle new message event from channels."""
            logger.debug(
                f'Event triggered: chat={event.chat}, chat_type={type(event.chat).__name__}, '
                f'chat_id={getattr(event.chat, "id", None)}, '
                f'message_id={event.message.id}, has_text={bool(event.message.text)}, '
                f'has_media={bool(event.message.media)}'
            )
            
            if not event.chat or not isinstance(event.chat, Channel):
                logger.debug(f'Filtered out: not a Channel (chat={event.chat})')
                return
            
            message = event.message
            
            if not message.text and not message.media:
                logger.debug(f'Filtered out message {message.id}: no text or media')
                return
            
            logger.info(
                f'New message from channel {event.chat.title or event.chat.username} '
                f'(ID: {message.id})'
            )
            
            if self.message_callback:
                try:
                    await self.message_callback(message, event.chat)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f'Error in message callback: {e}', exc_info=True)

        @self.client.on(events.NewMessage(chats=None))
        async def handle_private_message(event):
            """Handle forwarded messages from private chats."""
            from telethon.tl.types import User

            if not event.chat or isinstance(event.chat, Channel):
                return

            message = event.message

            if not message.text and not message.media:
                return

            if not message.forward:
                return

            # Safely get the 'from_' attribute which may not exist on all Forward objects
            from_chat = getattr(message.forward, 'from_', None)
            if not from_chat or not isinstance(from_chat, Channel):
                return

            from_chat_id = getattr(from_chat, 'id', None)
            if from_chat_id is None:
                return

            # Check if from_chat matches any monitored channel.
            # Contract: monitored_channel_ids contains whatever was stored from config —
            #   - str  "@username"
            #   - int  full negative ID  (-1001234567890)
            #   - int  bare positive ID  (1234567890)  — only if config had a bare number
            # Forward.from_.id is always the bare positive channel ID (no -100 prefix).
            matched = False
            for monitored_id in self.monitored_channel_ids:
                if isinstance(monitored_id, int) and monitored_id < 0:
                    # Full -100-prefixed ID → strip prefix to get bare ID for comparison.
                    # abs(-1001234567890) - 1_000_000_000_000 == 1234567890
                    bare_monitored = abs(monitored_id) - 1000000000000
                    if from_chat_id == bare_monitored:
                        matched = True
                        break
                elif isinstance(monitored_id, int):
                    if from_chat_id == monitored_id:
                        matched = True
                        break
                elif isinstance(monitored_id, str):
                    from_chat_username = getattr(from_chat, 'username', None)
                    if from_chat_username and f'@{from_chat_username}' == monitored_id:
                        matched = True
                        break

            if not matched:
                return

            logger.info(
                f'New forwarded message from channel {from_chat.title or from_chat.username} '
                f'(ID: {message.id})'
            )

            if self.message_callback:
                try:
                    await self.message_callback(message, from_chat)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f'Error in message callback: {e}', exc_info=True)

    async def run(self):
        """Run the Telegram client."""
        if not self.client:
            raise Exception('Telegram client not initialized')
        
        await self.start_monitoring()
        logger.info('Telegram monitor started')
        
        # Run until disconnected
        await self.client.run_until_disconnected()

    async def disconnect(self):
        """Disconnect Telegram client."""
        if self.client:
            await self.client.disconnect()
            logger.info('Telegram client disconnected')

    async def download_media(self, message) -> Optional[bytes]:
        """Download media from message to bytes.

        For files larger than _IN_MEMORY_LIMIT, returns None and logs a warning.
        Use download_media_to_file for large files.
        """
        if not message.media:
            return None

        try:
            size = getattr(getattr(message, 'media', None), 'filesize', None)
            if isinstance(size, (int, float)) and size > _IN_MEMORY_LIMIT:
                logger.info(
                    f'Media too large for in-memory download ({size / (1024*1024):.1f}MB), '
                    f'use download_media_to_file instead'
                )
                return None

            data = await message.download_media(file=bytes)
            if data:
                logger.debug(f'Downloaded {len(data)} bytes of media')
            return data
        except Exception as e:
            logger.error(f'Failed to download media: {e}')
            return None

    async def download_media_to_file(self, message) -> Optional[str]:
        """Download media from message to a temporary file.

        Returns the path to the temporary file, or None on failure.
        The caller is responsible for deleting the file when done.
        """
        if not message.media:
            return None

        try:
            suffix = '.bin'
            if hasattr(message, 'video') and message.video:
                suffix = '.mp4'
            elif hasattr(message, 'photo') and message.photo:
                suffix = '.jpg'

            fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix='tg_media_')
            os.close(fd)

            result = await message.download_media(file=temp_path)
            if result:
                file_size = os.path.getsize(temp_path)
                logger.debug(f'Downloaded media to temp file: {temp_path} ({file_size} bytes)')
                return temp_path
            else:
                os.unlink(temp_path)
                return None
        except Exception as e:
            logger.error(f'Failed to download media to file: {e}')
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
            return None
