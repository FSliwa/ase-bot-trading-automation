#!/bin/bash
# This script packages the application files for an update.

set -e

# Define the name of the update file with a timestamp
UPDATE_FILE="trading_bot_update_$(date +'%Y%m%d_%H%M%S').tar.gz"
echo "📦 Creating update package: $UPDATE_FILE"

# List of essential files and directories for the update
FILES_TO_PACKAGE=(
    "fastapi_app.py"
    "web/"
    "requirements.txt"
    "trading.db"
)

# Check if all files exist before packaging
for item in "${FILES_TO_PACKAGE[@]}"; do
    if [ ! -e "$item" ]; then
        echo "❌ Error: Required file or directory not found: $item"
        exit 1
    fi
done

# Create the compressed tarball
tar -czvf "$UPDATE_FILE" "${FILES_TO_PACKAGE[@]}"

echo "✅ Update package created successfully: $UPDATE_FILE"
echo "   You can now use this file to update the server."
