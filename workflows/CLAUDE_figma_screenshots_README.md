# Figma Screenshot Fetcher

Python script for Executor agents to fetch Figma design screenshots during implementation.

## Setup (One-time)

### 1. Install dependencies
```bash
pip install requests
```

### 2. Get Figma Personal Access Token
1. Go to https://www.figma.com/settings
2. Scroll to "Personal access tokens"
3. Click "Create a new personal access token"
4. Name it: "Coinsher Development"
5. Copy the token

### 3. Set environment variable
```bash
# Add to your ~/.zshrc or ~/.bashrc
export FIGMA_ACCESS_TOKEN="figd_your_token_here"

# Or set temporarily for current session
export FIGMA_ACCESS_TOKEN="figd_your_token_here"
```

## Usage

### Option 1: Using Figma URL (Easiest)
```bash
python CLAUDE_fetch_figma_screenshot.py \
  --url "https://www.figma.com/design/48MKltwBC6tZxu251lhpVU/coinsher-exchange-mobile-app?node-id=1-9366" \
  --output screenshots/figma/swap-page-mobile.png
```

### Option 2: Using file-key and node-id separately
```bash
python CLAUDE_fetch_figma_screenshot.py \
  --file-key 48MKltwBC6tZxu251lhpVU \
  --node-id 1-9366 \
  --output screenshots/figma/swap-page-mobile.png
```

### Advanced Options
```bash
python CLAUDE_fetch_figma_screenshot.py \
  --url "https://figma.com/design/FILE_KEY/name?node-id=1-9366" \
  --output screenshots/figma/component.png \
  --format png \
  --scale 2.0  # 2x for retina, 1.0 for standard
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--url` | One of url OR (file-key + node-id) | - | Full Figma URL with node-id |
| `--file-key` | One of url OR (file-key + node-id) | - | Figma file key from URL |
| `--node-id` | One of url OR (file-key + node-id) | - | Node ID (format: 1-9366 or 1:9366) |
| `--output` | Yes | - | Where to save screenshot |
| `--format` | No | png | Image format (png, jpg, svg, pdf) |
| `--scale` | No | 2.0 | Scaling factor (0.01 to 4.0) |

## Examples for Executor Workflow

### Milestone 1: Fetch design reference
```bash
# Create screenshots directory
mkdir -p screenshots/figma screenshots/browser

# Fetch mobile swap page design
python CLAUDE_fetch_figma_screenshot.py \
  --url "https://www.figma.com/design/48MKltwBC6tZxu251lhpVU/coinsher-exchange-mobile-app?node-id=1-9366" \
  --output screenshots/figma/swap-page-mobile-390w.png

# Fetch specific component (e.g., "From" card)
python CLAUDE_fetch_figma_screenshot.py \
  --file-key 48MKltwBC6tZxu251lhpVU \
  --node-id 1-9385 \
  --output screenshots/figma/swap-from-card.png
```

### Milestone N: Take browser screenshot for comparison
```bash
# Start dev server on available port
PORT=3001 npm run dev &
DEV_PID=$!

# Wait for server to be ready
sleep 5

# Take screenshot (using your preferred tool)
# Option 1: Using playwright
npx playwright screenshot http://localhost:3001/swap screenshots/browser/milestone-1-swap-page-390w.png --viewport-size=390,844

# Option 2: Using puppeteer
# node scripts/screenshot.js http://localhost:3001/swap screenshots/browser/milestone-1-swap-page.png

# Stop dev server
kill $DEV_PID
```

## Troubleshooting

### Error: "FIGMA_ACCESS_TOKEN environment variable not set"
**Solution:** Follow setup step 3 above to set your token

### Error: "Invalid token"
**Solutions:**
- Token may have expired - generate a new one
- Make sure you copied the entire token (starts with `figd_`)
- Token needs `file_content:read` scope

### Error: "No image URL returned for node"
**Solutions:**
- Check that node ID is correct (view in Figma URL)
- Node may be in a different frame - try parent node ID
- File key might be wrong - double-check Figma URL

## For Orchestrator: How to Get Node IDs

When creating implementation plans, use Figma MCP to explore the design:

```python
# In Orchestrator session, use MCP tools:
# 1. Get metadata to see node structure
mcp__figma-remote-mcp__get_metadata(fileKey="...", nodeId="0:1")  # Page level

# 2. Get specific component details
mcp__figma-remote-mcp__get_design_context(fileKey="...", nodeId="1-9366")

# 3. Include these node IDs in the implementation plan for Executor
```

## Security Note

**Never commit your FIGMA_ACCESS_TOKEN to git!**

The token is in an environment variable, so it won't be in code. But be careful not to:
- Print it in logs
- Add it to any committed files
- Share it in screenshots or reports
