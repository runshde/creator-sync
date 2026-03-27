# creator-sync

Local-first video publishing workflow for creator-owned media.

## Scope

This project is intended for:

- organizing locally stored videos
- preparing metadata for publishing
- uploading creator-owned or explicitly authorized videos to Bilibili

It is not intended for unauthorized downloading or reposting of third-party content.

## Initial Layout

- `config/`: local configuration files
- `data/inbox/`: videos waiting to be processed
- `data/processed/`: videos that finished successfully
- `data/failed/`: videos that need attention
- `logs/`: runtime logs
- `scripts/`: operational helper scripts
- `src/`: application code

## Next Steps

1. Define the uploader workflow and config format.
2. Add a local metadata manifest for each video.
3. Implement a minimal Bilibili upload runner.
4. Add logging, retries, and post-upload archiving.
