"""Media compression utilities."""

import logging
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


class MediaCompressor:
    """Compress media files to fit within size limits."""

    # Quality thresholds
    MIN_QUALITY = 60  # Minimum acceptable JPEG quality
    MAX_QUALITY = 95  # Maximum JPEG quality
    TARGET_QUALITY = 85  # Default target quality

    # Size thresholds
    MAX_COMPRESSION_RATIO = 0.3  # Don't compress if size reduction would be less than 30%
    MAX_SOURCE_SIZE_MB = 50  # Don't attempt to compress files larger than 50MB

    @staticmethod
    def can_compress(media_data: bytes, max_size_mb: int) -> Tuple[bool, str]:
        """
        Determine if media can be compressed to fit within max size without significant quality loss.
        
        Returns:
            Tuple of (can_compress, reason)
        """
        current_size_mb = len(media_data) / (1024 * 1024)
        
        # If already under limit, no compression needed
        if current_size_mb <= max_size_mb:
            return False, "File already within size limit"
        
        # If file is way too large, compression won't help
        if current_size_mb > MediaCompressor.MAX_SOURCE_SIZE_MB:
            return False, f"Source file too large ({current_size_mb:.1f}MB) for compression"
        
        # Check if this is an image
        try:
            Image.open(BytesIO(media_data))
            return True, "Image compression feasible"
        except Exception:
            # Not an image or unsupported format
            return False, "Not a compressible image format"
    
    @staticmethod
    async def compress_image(
        media_data: bytes,
        max_size_mb: int,
        filename: str = 'image.jpg'
    ) -> Optional[bytes]:
        """
        Compress an image to fit within max_size_mb.
        
        Args:
            media_data: Original image data
            max_size_mb: Maximum allowed size in MB
            filename: Original filename (to determine format)
            
        Returns:
            Compressed image data, or None if compression not feasible
        """
        can_compress, reason = MediaCompressor.can_compress(media_data, max_size_mb)
        if not can_compress:
            logger.debug(f"Cannot compress {filename}: {reason}")
            return None
        
        try:
            # Open image
            img = Image.open(BytesIO(media_data))
            
            # Convert to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Try to compress with progressive quality reduction
            target_size_bytes = max_size_mb * 1024 * 1024
            
            # Start with high quality and reduce if needed
            for quality in range(MediaCompressor.MAX_QUALITY, MediaCompressor.MIN_QUALITY - 1, -5):
                output = BytesIO()
                img.save(output, format='JPEG', quality=quality, optimize=True)
                compressed_data = output.getvalue()
                compressed_size_mb = len(compressed_data) / (1024 * 1024)
                
                logger.debug(f"Quality {quality}: {compressed_size_mb:.2f}MB (target: {max_size_mb}MB)")
                
                if compressed_size_mb <= target_size_mb:
                    # Check if compression ratio is acceptable
                    original_size_mb = len(media_data) / (1024 * 1024)
                    compression_ratio = compressed_size_mb / original_size_mb
                    
                    if compression_ratio < MediaCompressor.MAX_COMPRESSION_RATIO:
                        logger.info(
                            f"Compressed {filename}: {original_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB "
                            f"(quality: {quality}, ratio: {compression_ratio:.2%})"
                        )
                        return compressed_data
                    else:
                        logger.debug(
                            f"Compression ratio {compression_ratio:.2%} too low, quality: {quality}"
                        )
                        break
            
            # If we get here, couldn't compress to target size with acceptable quality
            logger.warning(f"Could not compress {filename} to {max_size_mb}MB with acceptable quality")
            return None
            
        except Exception as e:
            logger.error(f"Error compressing {filename}: {e}", exc_info=True)
            return None
    
    @staticmethod
    async def compress_media(
        media_data: bytes,
        media_type: str,
        max_size_mb: int,
        filename: str = 'file'
    ) -> Optional[bytes]:
        """
        Compress media based on type.
        
        Args:
            media_data: Original media data
            media_type: Type of media ('photo', 'video', 'document')
            max_size_mb: Maximum allowed size in MB
            filename: Original filename
            
        Returns:
            Compressed media data, or None if compression not feasible
        """
        if media_type == 'photo':
            return await MediaCompressor.compress_image(media_data, max_size_mb, filename)
        else:
            # Video and document compression not implemented yet
            # Videos are too complex for in-memory compression
            # Documents should not be compressed (may become corrupted)
            logger.debug(f"Compression not implemented for media type: {media_type}")
            return None
