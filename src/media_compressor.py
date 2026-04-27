"""Media compression utilities."""

import logging
import subprocess
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image

try:
    import ffmpeg
    HAS_FFMPEG_PYTHON = True
except ImportError:
    ffmpeg = None
    HAS_FFMPEG_PYTHON = False

logger = logging.getLogger(__name__)


class MediaCompressor:
    """Compress media files to fit within size limits."""

    # Quality thresholds
    MIN_QUALITY = 60  # Minimum acceptable JPEG quality
    MAX_QUALITY = 95  # Maximum JPEG quality
    TARGET_QUALITY = 85  # Default target quality

    # Size thresholds
    MAX_COMPRESSION_RATIO = 0.3  # Don't compress if size reduction would be less than 30%
    MAX_SOURCE_SIZE_MB = 200  # Don't attempt to compress files larger than this
    MAX_VIDEO_SOURCE_SIZE_MB = 500  # Maximum video size to attempt compression

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
            img = Image.open(BytesIO(media_data))
            img.verify()
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
                
                if compressed_size_mb <= max_size_mb:
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
    async def compress_video(
        media_data: bytes,
        max_size_mb: int,
        filename: str = 'video.mp4'
    ) -> Optional[bytes]:
        """
        Compress a video to fit within max_size_mb.
        
        Args:
            media_data: Original video data
            max_size_mb: Maximum allowed size in MB
            filename: Original filename
            
        Returns:
            Compressed video data, or None if compression not feasible
        """
        current_size_mb = len(media_data) / (1024 * 1024)
        
        # If already under limit, no compression needed
        if current_size_mb <= max_size_mb:
            return None
        
        # If file is way too large, compression won't help
        if current_size_mb > MediaCompressor.MAX_VIDEO_SOURCE_SIZE_MB:
            logger.debug(f"Video too large ({current_size_mb:.1f}MB) for compression")
            return None
        
        # Check if ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.debug("ffmpeg not available for video compression")
            return None
        
        # Check if ffmpeg-python is available
        if not HAS_FFMPEG_PYTHON:
            logger.debug("ffmpeg-python not available for video compression")
            return None
        
        try:
            import tempfile
            import os
            
            # First, validate the video data is complete and readable
            if not await MediaCompressor._validate_video(media_data, filename):
                logger.debug(f"Video validation failed for {filename}")
                return None
            
            # Write video to temporary file for better ffmpeg handling
            # Using a temp file instead of pipe allows ffmpeg to seek and analyze properly
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_input:
                temp_input.write(media_data)
                temp_input_path = temp_input.name
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_output:
                temp_output_path = temp_output.name
            
            try:
                target_size_bytes = max_size_mb * 1024 * 1024
            
                # Calculate target bitrate (in bits per second)
                duration = await MediaCompressor._get_video_duration(media_data)
                if duration is None:
                    logger.debug(f"Could not get video duration for {filename}")
                    return None
                
                # Target bitrate with 10% overhead for container
                target_bitrate = int((target_size_bytes * 8) / duration * 0.9)
                
                # Ensure minimum bitrate for quality
                min_bitrate = 500 * 1024  # 500 kbps
                if target_bitrate < min_bitrate:
                    logger.debug(
                        f"Target bitrate {target_bitrate/1024:.0f}kbps too low for {filename}, "
                        f"using minimum {min_bitrate/1024:.0f}kbps"
                    )
                    target_bitrate = min_bitrate
                
                logger.debug(
                    f"Compressing {filename}: {current_size_mb:.2f}MB -> {max_size_mb}MB, "
                    f"bitrate: {target_bitrate/1024:.0f}kbps, duration: {duration:.1f}s"
                )
                
                # Build ffmpeg command using temp files instead of pipe
                # This allows ffmpeg to seek and properly analyze the video
                (
                    ffmpeg
                    .input(temp_input_path, analyzeduration='20000000', probesize='100000000')
                    .output(
                        temp_output_path,
                        vcodec='libx264',
                        acodec='aac',
                        video_bitrate=f'{target_bitrate}',
                        audio_bitrate='128k',
                        preset='medium',
                        movflags='faststart',
                        fflags='+genpts+discardcorrupt'  # Generate PTS and discard corrupt packets
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True, timeout=120)
                )
                
                # Read the compressed video from temp file
                with open(temp_output_path, 'rb') as f:
                    output = f.read()
                
                compressed_size_mb = len(output) / (1024 * 1024)
                
                if compressed_size_mb > max_size_mb:
                    logger.debug(
                        f"Compressed video {compressed_size_mb:.2f}MB still exceeds limit {max_size_mb}MB"
                    )
                    return None
                
                logger.info(
                    f"Compressed {filename}: {current_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB"
                )
                return output
            finally:
                # Clean up temporary files
                try:
                    os.unlink(temp_input_path)
                except (OSError, IOError):
                    pass
                try:
                    os.unlink(temp_output_path)
                except (OSError, IOError):
                    pass
        except Exception as e:
            logger.error(f"Error compressing video {filename}: {e}", exc_info=True)
            return None
    
    @staticmethod
    async def _get_video_duration(media_data: bytes) -> Optional[float]:
        """Get video duration using ffprobe via pipe."""
        try:
            import json
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'error',
                    '-analyzeduration', '10000000',
                    '-probesize', '50000000',
                    '-print_format', 'json',
                    '-show_format',
                    'pipe:0'
                ],
                input=media_data,
                capture_output=True,
                timeout=60
            )
            if result.returncode != 0:
                logger.debug(f"ffprobe failed: {result.stderr.decode('utf-8', errors='ignore')}")
                return None
            probe = json.loads(result.stdout)
            duration = float(probe['format']['duration'])
            return duration
        except subprocess.TimeoutExpired:
            logger.debug("ffprobe timeout while getting video duration")
            return None
        except Exception as e:
            logger.debug(f"Error getting video duration: {e}")
            return None
    
    @staticmethod
    async def _validate_video(media_data: bytes, filename: str) -> bool:
        """Validate that the video data is complete and readable."""
        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'error',
                    '-analyzeduration', '10000000',
                    '-probesize', '50000000',
                    '-show_entries', 'format=duration,size,bit_rate',
                    '-of', 'default=noprint_wrappers=1',
                    'pipe:0'
                ],
                input=media_data,
                capture_output=True,
                timeout=60
            )
            if result.returncode != 0:
                logger.debug(f"Video validation failed for {filename}: {result.stderr.decode('utf-8', errors='ignore')}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.debug(f"Video validation timeout for {filename}")
            return False
        except Exception as e:
            logger.debug(f"Error validating video {filename}: {e}")
            return False
    
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
        elif media_type == 'video':
            return await MediaCompressor.compress_video(media_data, max_size_mb, filename)
        else:
            # Document compression not implemented
            # Documents should not be compressed (may become corrupted)
            logger.debug(f"Compression not implemented for media type: {media_type}")
            return None
