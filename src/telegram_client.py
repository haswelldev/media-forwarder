"""Telegram client for monitoring channels."""

import logging
from typing import Optional
from telethon import TelegramClient, events
from telethon.tl.types import Channel, MessageMediaPhoto, MessageMediaDocument
from .config import ConfigManager

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
            
            # Connect to Telegram
            await self.client.connect()
            
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
                    # Numeric channel ID - convert to integer
                    channel_id = int(channel_id)

                # Try to resolve the channel
                entity = await self.client.get_input_entity(channel_id)
                # Use the full channel ID (with -100 prefix) for event filtering
                # The chats parameter in NewMessage needs the full channel ID
                entity_id = getattr(entity, 'channel_id', getattr(entity, 'id', None))
                if entity_id is None:
                    logger.error(f'Could not extract ID from entity for {channel_config.channel}')
                    continue

                # For channels, use the full ID with -100 prefix
                if isinstance(entity, Channel) and hasattr(entity, 'channel_id'):
                    full_id = -1000000000000 + entity.channel_id
                    channels_to_monitor.append(full_id)
                else:
                    channels_to_monitor.append(entity_id)

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

            # Calculate full channel ID (with -100 prefix) for comparison
            from_chat_id = from_chat.id
            if hasattr(from_chat, 'channel_id'):
                from_chat_full_id = -1000000000000 + from_chat.channel_id
            else:
                from_chat_full_id = from_chat.id

            if from_chat_full_id not in self.monitored_channel_ids:
                return

            logger.info(
                f'New forwarded message from channel {from_chat.title or from_chat.username} '
                f'(ID: {message.id})'
            )

            if self.message_callback:
                try:
                    await self.message_callback(message, from_chat)
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
        """Download media from message to bytes."""
        if not message.media:
            return None
        
        try:
            data = await message.download_media(file=bytes)
            logger.debug(f'Downloaded {len(data)} bytes of media')
            return data
        except Exception as e:
            logger.error(f'Failed to download media: {e}')
            return None
