#!/bin/sh
set -e

TARGET_DIR="${1:-.}"
cd "$TARGET_DIR"

ROOT_DIR=$(git rev-parse --show-toplevel)
cd "$ROOT_DIR"

echo "Resolving Git symlinks in $ROOT_DIR..."
SYMLINKS=$(git ls-files -s | grep '^120000' | cut -f2)

for sl in $SYMLINKS
do
    TARGET_REL=$(git cat-file blob ":$sl" 2>/dev/null | tr -d '\r\n') || true
    if [ -n "$TARGET_REL" ]; then
        TARGET=$(dirname "$sl")/"$TARGET_REL"
        if [ -e "$TARGET" ]; then
            rm -rf "$sl"
            cp -r "$TARGET" "$sl"
            git update-index --assume-unchanged "$sl" 2>/dev/null || true
        fi
    fi
done

echo "Symlinks resolved successfully in $ROOT_DIR."
