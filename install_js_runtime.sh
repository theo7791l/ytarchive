#!/bin/bash

# Script to install JavaScript runtime for yt-dlp challenge solving
# This fixes "n challenge solving failed" and "Signature solving failed" errors

echo "========================================"
echo "Installing JavaScript Runtime for yt-dlp"
echo "========================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run with sudo or as root"
    exit 1
fi

# Install Node.js (required for YouTube challenge solving)
echo "\nInstalling Node.js..."
apt-get update
apt-get install -y nodejs npm

# Verify installation
echo "\nVerifying installation..."
node --version
npm --version

echo "\n========================================"
echo "Installation complete!"
echo "========================================"
echo "\nyt-dlp can now solve YouTube JavaScript challenges."
echo "Restart your application to apply changes."
echo "\nUsage: sudo bash install_js_runtime.sh"
