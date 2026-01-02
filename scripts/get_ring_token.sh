#!/bin/bash
# Get a fresh Ring refresh token using ring-client-api CLI

echo "========================================="
echo "Ring Refresh Token Generator"
echo "========================================="
echo ""
echo "This script will help you obtain a fresh Ring refresh token."
echo "You'll need your Ring username and password, and 2FA code if enabled."
echo ""

cd "$(dirname "$0")"
npx -p ring-client-api ring-auth-cli
