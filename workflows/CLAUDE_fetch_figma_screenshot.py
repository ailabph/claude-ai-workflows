#!/usr/bin/env python3
"""
Figma Screenshot Fetcher for Executor Agent

This script allows the Executor agent to fetch screenshots from Figma designs
and save them to the screenshots/figma/ directory for implementation reference.

Usage:
    python CLAUDE_fetch_figma_screenshot.py \
        --file-key 48MKltwBC6tZxu251lhpVU \
        --node-id 1-9366 \
        --output screenshots/figma/swap-page-mobile.png

Requirements:
    - FIGMA_ACCESS_TOKEN environment variable must be set
    - pip install requests

To get a Figma access token:
    1. Go to https://www.figma.com/settings
    2. Scroll to "Personal access tokens"
    3. Click "Create a new personal access token"
    4. Copy the token and set it as an environment variable:
       export FIGMA_ACCESS_TOKEN="your-token-here"
"""

import os
import sys
import argparse
import requests
from pathlib import Path
from typing import Optional


def fetch_figma_screenshot(
    file_key: str,
    node_id: str,
    output_path: str,
    format: str = "png",
    scale: float = 2.0,
    figma_token: Optional[str] = None
) -> bool:
    """
    Fetch a screenshot from Figma and save it to a file.

    Args:
        file_key: Figma file key (from URL)
        node_id: Node ID to screenshot (e.g., "1-9366")
        output_path: Path to save the screenshot
        format: Image format (png, jpg, svg, pdf)
        scale: Scaling factor (0.01 to 4)
        figma_token: Figma access token (defaults to env var)

    Returns:
        True if successful, False otherwise
    """
    # Get token from environment if not provided
    if not figma_token:
        figma_token = os.getenv("FIGMA_ACCESS_TOKEN")

    if not figma_token:
        print("❌ Error: FIGMA_ACCESS_TOKEN environment variable not set")
        print("\nTo fix this:")
        print("1. Go to https://www.figma.com/settings")
        print("2. Generate a personal access token")
        print("3. Run: export FIGMA_ACCESS_TOKEN='your-token-here'")
        return False

    # Convert node ID format (1-9366 or 1:9366 both work)
    node_id_formatted = node_id.replace("-", ":")

    # Step 1: Get image URL from Figma API
    api_url = f"https://api.figma.com/v1/images/{file_key}"
    params = {
        "ids": node_id_formatted,
        "format": format,
        "scale": scale
    }
    headers = {
        "Authorization": f"Bearer {figma_token}"
    }

    print(f"📡 Fetching image URL from Figma API...")
    print(f"   File: {file_key}")
    print(f"   Node: {node_id_formatted}")

    response = requests.get(api_url, params=params, headers=headers)

    if response.status_code != 200:
        print(f"❌ Error: Failed to get image URL (status {response.status_code})")
        print(f"   Response: {response.text}")
        return False

    data = response.json()

    if data.get("err"):
        print(f"❌ Error from Figma API: {data['err']}")
        return False

    images = data.get("images", {})
    image_url = images.get(node_id_formatted)

    if not image_url:
        print(f"❌ Error: No image URL returned for node {node_id_formatted}")
        print(f"   Available nodes: {list(images.keys())}")
        return False

    # Step 2: Download the image
    print(f"⬇️  Downloading image from Figma CDN...")
    image_response = requests.get(image_url)

    if image_response.status_code != 200:
        print(f"❌ Error: Failed to download image (status {image_response.status_code})")
        return False

    # Step 3: Save to file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_file.write_bytes(image_response.content)

    file_size = len(image_response.content) / 1024  # KB
    print(f"✅ Screenshot saved to: {output_path}")
    print(f"   File size: {file_size:.1f} KB")

    return True


def parse_figma_url(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse Figma URL to extract file key and node ID.

    Example URLs:
        https://www.figma.com/design/48MKltwBC6tZxu251lhpVU/coinsher-exchange-mobile-app?node-id=1-9366
        https://figma.com/file/48MKltwBC6tZxu251lhpVU?node-id=1-9366

    Returns:
        (file_key, node_id) or (None, None) if parsing fails
    """
    import re

    # Extract file key (alphanumeric string after /design/ or /file/)
    file_match = re.search(r'/(?:design|file)/([a-zA-Z0-9]+)', url)
    file_key = file_match.group(1) if file_match else None

    # Extract node ID (from node-id= query param)
    node_match = re.search(r'node-id=([0-9-]+)', url)
    node_id = node_match.group(1) if node_match else None

    return file_key, node_id


def main():
    parser = argparse.ArgumentParser(
        description="Fetch screenshots from Figma designs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Option 1: Provide URL directly
    parser.add_argument(
        "--url",
        help="Figma URL (e.g., https://figma.com/design/FILE_KEY/name?node-id=1-9366)"
    )

    # Option 2: Provide file-key and node-id separately
    parser.add_argument(
        "--file-key",
        help="Figma file key (from URL)"
    )
    parser.add_argument(
        "--node-id",
        help="Node ID to screenshot (e.g., 1-9366 or 1:9366)"
    )

    # Output options
    parser.add_argument(
        "--output",
        required=True,
        help="Output path (e.g., screenshots/figma/swap-page.png)"
    )
    parser.add_argument(
        "--format",
        default="png",
        choices=["png", "jpg", "svg", "pdf"],
        help="Image format (default: png)"
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=2.0,
        help="Scaling factor 0.01-4 (default: 2.0 for retina)"
    )

    args = parser.parse_args()

    # Parse inputs
    file_key = args.file_key
    node_id = args.node_id

    if args.url:
        # Parse URL to extract file_key and node_id
        parsed_file_key, parsed_node_id = parse_figma_url(args.url)
        file_key = file_key or parsed_file_key
        node_id = node_id or parsed_node_id

    # Validate inputs
    if not file_key or not node_id:
        print("❌ Error: Must provide either --url OR both --file-key and --node-id")
        parser.print_help()
        sys.exit(1)

    # Fetch screenshot
    success = fetch_figma_screenshot(
        file_key=file_key,
        node_id=node_id,
        output_path=args.output,
        format=args.format,
        scale=args.scale
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()