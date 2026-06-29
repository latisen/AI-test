#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$ROOT_DIR/backups/backup_$STAMP"

mkdir -p "$DEST"

for dir in characters memories images loras workflows qdrant logs docker/openwebui reference_photos; do
  if [[ -d "$ROOT_DIR/$dir" ]]; then
    cp -a "$ROOT_DIR/$dir" "$DEST/"
  fi
done

tar -C "$ROOT_DIR/backups" -czf "$ROOT_DIR/backups/backup_$STAMP.tar.gz" "backup_$STAMP"
rm -rf "$DEST"

echo "Backup completed: $ROOT_DIR/backups/backup_$STAMP.tar.gz"
