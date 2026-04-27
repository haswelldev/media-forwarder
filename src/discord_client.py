"""Discord client for sending messages via webhooks."""

import logging
from typing import Optional, List
import discord
from io import BytesIO

logger = logging.getLogger(__name__)


class DiscordSender:
    """Send messages to Discord via webhooks."""

    def __init__(self, webhook_url: str, max_file_size_mb: int = 10):
        """Initialize Discord sender."""
        self.webhook_url = webhook_url
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    async def send_message(
        self,
        text: Optional[str] = None,
        media_data: Optional[bytes] = None,
        filename: str = 'file'
    ) -> bool:
        """Send message to Discord."""
        try:
            # Create webhook sync adapter (discord.py uses async)
            webhook = discord.Webhook.from_url(
                self.webhook_url,
                adapter=discord.RequestsWebhookAdapter()
            )

            # Send text only
            if not media_data:
                if text:
                    webhook.send(content=text)
                else:
                    logger.warning('No content to send')
                    return False
            else:
                # Check file size
                if len(media_data) > self.max_file_size_bytes:
                    logger.warning(
                        f'File too large: {len(media_data) / (1024 * 1024):.2f}MB '
                        f'(max: {self.max_file_size_mb}MB), skipping'
                    )
                    # Send text only if available
                    if text:
                        webhook.send(content=text)
                    return False

                # Send with media
                file = discord.File(
                    BytesIO(media_data),
                    filename=filename
                )
                
                if text:
                    webhook.send(content=text, file=file)
                else:
                    webhook.send(file=file)

            logger.info(f'Message sent to Discord successfully')
            return True

        except discord.errors.HTTPException as e:
            logger.error(f'Discord HTTP error: {e}')
            return False
        except Exception as e:
            logger.error(f'Failed to send to Discord: {e}', exc_info=True)
            return False

    async def send_photo(
        self,
        text: Optional[str],
        photo_data: bytes
    ) -> bool:
        """Send photo to Discord."""
        return await self.send_message(text, photo_data, 'photo.jpg')

    async def send_video(
        self,
        text: Optional[str],
        video_data: bytes,
        filename: str = 'video.mp4'
    ) -> bool:
        """Send video to Discord."""
        return await self.send_message(text, video_data, filename)

    async def send_document(
        self,
        text: Optional[str],
        document_data: bytes,
        filename: str = 'document'
    ) -> bool:
        """Send document to Discord."""
        return await self.send_message(text, document_data, filename)
