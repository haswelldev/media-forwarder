# Media Forwarder

A Dockerized service that monitors Telegram channels and automatically forwards posts (including photos, videos, and documents) to Discord channels via webhooks.

## Features

- 📱 Monitor multiple Telegram channels simultaneously
- 🎯 Forward to multiple Discord destinations
- 📸 Support for photos, videos, and documents
- 🚫 Automatic filtering of oversized files (configurable)
- 🔒 Uses real Telegram user account (no bot limitations)
- 🐳 Docker-based deployment
- ⚙️ Simple YAML configuration
- 📊 Structured logging
- 💾 Session file persistence
- 🎨 **Per-channel settings** - Customize behavior per channel
- 📷 **Media-only mode** - Forward only messages with media
- 🔇 **Caption removal** - Strip captions from media posts
- 🌐 **Auto-translation** - Translate captions to English

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Telegram account with 2FA disabled (or password ready)
- Discord webhook URL(s)
- Telegram API credentials (get from [my.telegram.org](https://my.telegram.org))

### 1. Get Telegram API Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Sign in with your phone number
3. Go to "API development tools"
4. Create a new application (any name and description)
5. Copy the `api_id` and `api_hash`

### 2. Create Configuration Files

Create a `.env` file:

```bash
# Telegram API credentials
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here

# Optional: Session file name (default: media_forwarder)
TELEGRAM_SESSION_NAME=media_forwarder

# Optional: Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

Create a `config/channels.yaml` file:

```yaml
channels:
  - channel: "@channel_name_to_monitor"
    destinations:
      - discord_main

discord_webhooks:
  discord_main:
    url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

settings:
  max_file_size_mb: 10
  log_level: INFO
  include_channel_name: true
  include_timestamp: true
```

### 3. Login to Telegram

Run the login command (interactive):

```bash
docker compose run --rm media-forwarder python -m src.main login
```

Follow the prompts:
1. Enter your phone number (with country code, e.g., +1234567890)
2. Enter the verification code sent to Telegram
3. Enter your 2FA password if enabled

The session file will be saved to `./sessions/media_forwarder.session`

### 4. Validate Configuration

Check your configuration:

```bash
docker compose run --rm media-forwarder python -m src.main validate
```

### 5. Start the Service

```bash
docker compose up -d
```

### 6. View Logs

```bash
docker compose logs -f
```

## Configuration

### Channel Format

Channels can be specified by username or numeric ID:

```yaml
channels:
  # By username
  - channel: "@example_channel"
  
  # By numeric ID
  - channel: "-1001234567890"
```

### Per-Channel Settings

Each channel can have its own settings to override the defaults:

```yaml
channels:
  - channel: "@media_channel"
    destinations:
      - discord_main
    settings:
      # Only forward messages with media
      media_only: true
      # Remove captions from media posts
      remove_captions: false
      # Translate captions to English
      translate_captions: true
      # Custom max file size for this channel
      max_file_size_mb: 25
      # Override metadata inclusion
      include_channel_name: true
      include_timestamp: true
```

**Available Channel Settings:**

- `media_only` (bool): Only forward messages with media (photos, videos, documents). Skip text-only posts.
- `remove_captions` (bool): Remove captions from media posts.
- `translate_captions` (bool): Automatically translate captions to English.
- `max_file_size_mb` (int): Override maximum file size for this channel.
- `include_channel_name` (bool): Override include channel name setting.
- `include_timestamp` (bool): Override include timestamp setting.

### Multiple Destinations

Forward a channel to multiple Discord webhooks:

```yaml
channels:
  - channel: "@my_channel"
    destinations:
      - discord_main
      - discord_backup
```

### Settings

```yaml
settings:
  # Maximum file size in MB to upload to Discord
  # Files larger than this will be skipped
  max_file_size_mb: 10
  
  # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_level: INFO
  
  # Include channel name in forwarded messages
  include_channel_name: true
  
  # Include timestamp in forwarded messages
  include_timestamp: true
```

## Commands

### Login

Perform interactive login to Telegram:

```bash
docker compose run --rm media-forwarder python -m src.main login
```

### Run

Start the forwarder:

```bash
docker compose up -d
```

### Validate

Validate configuration:

```bash
docker compose run --rm media-forwarder python -m src.main validate
```

### Stop

Stop the service:

```bash
docker compose down
```

## File Size Limits

- **Telegram**: 2GB for Premium, 500MB for free accounts
- **Discord**: 25MB for free tier, 500MB for Nitro
- **Default limit**: 10MB (configurable)

Files larger than the configured limit are skipped, but the text message is still forwarded.

## Session Management

The Telegram session file is stored in `./sessions/` directory:

- Session name: `media_forwarder.session` (configurable)
- Location: Mounted as Docker volume
- Persistence: Survives container restarts
- Security: Contains authentication tokens, keep it private

To re-login, delete the session file and run the login command again:

```bash
rm ./sessions/media_forwarder.session
docker compose run --rm media-forwarder python -m src.main login
```

## Troubleshooting

### Session Not Authorized

**Error**: `Session is not authorized`

**Solution**: Run the login command to create a new session

```bash
docker compose run --rm media-forwarder python -m src.main login
```

### Channel Not Found

**Error**: `Channel not found` or `No configuration found for channel`

**Solution**: 
- Verify the channel username or ID in `config/channels.yaml`
- Make sure your Telegram account has access to the channel
- Try using the numeric ID instead of username

### Discord Webhook Failed

**Error**: `Failed to send to Discord`

**Solution**:
- Verify the webhook URL is correct
- Check Discord server status
- Ensure the webhook has permissions to post in the channel
- Check logs for detailed error messages

### File Too Large

**Warning**: `File too large: XX.XXMB (max: 10MB), skipping`

**Solution**: 
- Increase `max_file_size_mb` in configuration
- Note: Discord has hard limits (25MB free, 500MB Nitro)

## Development

### Building Locally

```bash
docker build -t media-forwarder .
```

### Running Locally

```bash
docker run --rm \
  -v $(pwd)/sessions:/app/sessions \
  -v $(pwd)/config:/app/config \
  --env-file .env \
  media-forwarder
```

## Development

### Running Tests

Run the test suite:

```bash
docker compose run --rm media-forwarder pytest tests/ -v
```

Run tests with coverage:

```bash
docker compose run --rm media-forwarder pytest tests/ -v --cov=src --cov-report=html
```

### Building Locally

```bash
docker build -t media-forwarder .
```

### Running Locally

```bash
docker run --rm \
  -v $(pwd)/sessions:/app/sessions \
  -v $(pwd)/config:/app/config \
  --env-file .env \
  media-forwarder
```

## CI/CD

This project uses GitHub Actions for:

- **Automated Testing**: Runs tests on every push and pull request
- **Docker Image Building**: Builds and pushes Docker images to GitHub Container Registry
- **Coverage Reporting**: Uploads coverage reports to Codecov

The Docker image is available at: `ghcr.io/haswelldev/media-forwarder:main`

## Architecture

- **Telegram Client**: Telethon (MTProto library for user accounts)
- **Discord Client**: discord.py (webhook-based)
- **Configuration**: YAML with Pydantic validation
- **Container**: Multi-stage Docker build with Python 3.11-slim
- **Testing**: pytest with asyncio support and coverage reporting

## Security

- Session files contain authentication tokens - keep them private
- API credentials should be stored in environment variables
- Webhook URLs should be kept secret
- Never commit `.env` files or session files to version control

## License

MIT

## Support

For issues and questions, please open an issue on GitHub.
