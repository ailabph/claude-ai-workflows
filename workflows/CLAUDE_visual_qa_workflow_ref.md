# Visual QA Workflow - Human Reference

Setup guide and reference for `CLAUDE_visual_qa_workflow.md`.

---

## Automated Setup (Recommended)

Run the setup script to check dependencies and configure automatically:

```bash
# Check what's installed/configured
python CLAUDE_visual_qa_workflow_setup.py

# Install missing dependencies
python CLAUDE_visual_qa_workflow_setup.py --install

# Configure MCP and permissions
python CLAUDE_visual_qa_workflow_setup.py --configure

# Full setup (install + configure)
python CLAUDE_visual_qa_workflow_setup.py --install --configure
```

---

## Manual Setup

### 1. Install Browser MCP

**Option A: Playwright MCP (Recommended)**
```bash
npm install -g @anthropic/mcp-server-playwright
```

**Option B: Puppeteer MCP**
```bash
npm install -g @anthropic/mcp-server-puppeteer
```

**Option C: Browserbase (Cloud)**
```bash
npm install -g @anthropic/mcp-server-browserbase
```

### 2. Configure Claude Code

Create or update `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    }
  }
}
```

Or for global config, add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    }
  }
}
```

### 3. Optional: Add Figma MCP

For fetching design specs directly from Figma:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    },
    "figma": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-figma"],
      "env": {
        "FIGMA_ACCESS_TOKEN": "your-token-here"
      }
    }
  }
}
```

### 4. Set Permissions

Create `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__playwright__*",
      "mcp__figma__*",
      "Bash(npm run dev)",
      "Bash(npm run build)",
      "Bash(git status)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Read",
      "Write",
      "Edit",
      "Glob",
      "Grep"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(git push:*)",
      "Bash(git reset --hard:*)"
    ]
  }
}
```

### 5. Start Dev Server

Before running visual QA:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
```

Verify server is accessible at the expected URL (e.g., `localhost:3000`).

---

## Kickstart Prompts

### Single Screen
```
Read CLAUDE_visual_qa_workflow.md.

Match this screen to the design.
- Route: /dashboard
- Dev server: localhost:3000
- Design: [paste image or Figma URL]

Viewport: 1280x720
```

### Multi-Screen Batch
```
Read CLAUDE_visual_qa_workflow.md.

Match these screens to their Figma designs:
1. /homepage - [figma-url-1]
2. /dashboard - [figma-url-2]
3. /settings - [figma-url-3]

Dev server: localhost:3000
Viewport: 1280x720
Checkpoint: after each screen
```

### Mobile Testing
```
Read CLAUDE_visual_qa_workflow.md.

Match /homepage to mobile design.
- Dev server: localhost:3000
- Design: [paste image]
- Viewport: 390x844
```

---

## Viewport Presets

| Name | Dimensions | Device |
|------|------------|--------|
| Desktop | 1280x720 | Standard laptop |
| Desktop Large | 1920x1080 | Full HD monitor |
| Tablet | 768x1024 | iPad portrait |
| Tablet Landscape | 1024x768 | iPad landscape |
| Mobile | 390x844 | iPhone 14/15 |
| Mobile Small | 375x667 | iPhone SE |
| Mobile Large | 428x926 | iPhone 14 Plus |

---

## Configuration Options

Specify in your task prompt:

| Option | Values | Default |
|--------|--------|---------|
| `Viewport` | `{width}x{height}` | 1280x720 |
| `Checkpoint` | `every_screen`, `every_3`, `on_completion` | every_screen |
| `Max attempts` | Number | 3 |
| `Confidence threshold` | Percentage | 90% |
| `Git commits` | `yes`, `no` | yes |

**Example:**
```
Viewport: 390x844
Checkpoint: every_3
Max attempts: 5
Git commits: yes
```

---

## Browser MCP Tools Reference

Typical tools available (names vary by implementation):

| Tool | Description | Example |
|------|-------------|---------|
| `browser_navigate` | Go to URL | `browser_navigate("http://localhost:3000/dashboard")` |
| `browser_screenshot` | Capture viewport | `browser_screenshot()` |
| `browser_set_viewport` | Set dimensions | `browser_set_viewport(1280, 720)` |
| `browser_click` | Click element | `browser_click(".button-primary")` |
| `browser_fill` | Type into input | `browser_fill("#email", "test@example.com")` |
| `browser_scroll` | Scroll page | `browser_scroll("down", 500)` |
| `browser_wait` | Wait for element | `browser_wait(".loaded", 5000)` |
| `browser_evaluate` | Run JavaScript | `browser_evaluate("document.title")` |
| `browser_close` | Close browser | `browser_close()` |

---

## Checkpoint Responses

How to respond when agent checkpoints:

| Intent | Say |
|--------|-----|
| Approve, continue | "Approved" or "Looks good, next" |
| Minor feedback | "Fix the button padding, then continue" |
| Major feedback | "The header is wrong, see [image]" |
| Skip screen | "Skip this, move to next" |
| Abort session | "Stop here" |

---

## Escalation Responses

When agent escalates with options:

| Situation | Response |
|-----------|----------|
| Can't match exact spec | "Use shadow-md, close enough" |
| Need exact value | "The shadow is: 0 4px 12px rgba(0,0,0,0.15)" |
| Skip issue | "Skip the shadow, continue" |
| Keep trying | "Try shadow-xl" |

---

## Troubleshooting

### Browser MCP not connecting

```bash
# Verify MCP server is installed
npx @anthropic/mcp-server-playwright --version

# Check Claude Code sees the MCP
# In Claude Code, run: /mcp
```

### Screenshots not capturing

1. Verify dev server is running
2. Check URL is correct (`localhost` vs `127.0.0.1`)
3. Increase wait time: "Wait 3 seconds after navigation"
4. Check for auth/login requirements

### Wrong viewport

Specify explicitly in prompt:
```
Viewport: 390x844 (exact)
```

### Comparison seems off

- Provide clearer design reference (higher resolution)
- Use Figma MCP for exact specs instead of image
- Lower confidence threshold: "Confidence threshold: 80%"

### Auth-protected routes

Option 1: Test on routes that don't require auth
Option 2: Provide login steps:
```
Before capturing, login:
1. Navigate to /login
2. Fill email: test@example.com
3. Fill password: testpass
4. Click submit
5. Wait for redirect
```

### Slow iteration

- Reduce wait time if pages load fast
- Use `on_completion` checkpoint for fewer interruptions
- Batch screens with `every_3` checkpoint

---

## Files Overview

| File | Purpose | Audience |
|------|---------|----------|
| `CLAUDE_visual_qa_workflow.md` | Workflow instructions | Agent |
| `CLAUDE_visual_qa_workflow_ref.md` | Setup & reference | Human |

---

## Comparison: Manual vs Autonomous

| Aspect | Manual (frontend_refactor) | Autonomous (visual_qa) |
|--------|---------------------------|------------------------|
| Setup required | None | Browser MCP |
| Screenshots by | Human | Agent |
| Iteration speed | Slow (human bottleneck) | Fast (autonomous) |
| Best for | Subjective UI polish | Pixel-accurate matching |
| Human involvement | Every iteration | Checkpoints only |
| Works offline | Yes | Yes (local browser) |

**Use Manual when:** You need subjective feedback, design is ambiguous, no MCP setup

**Use Autonomous when:** Clear design specs, need speed, multiple screens to match

---

## Custom Browser MCP

If existing MCPs don't meet your needs, create a custom one:

### Basic Template

```typescript
// mcp-browser/index.ts
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { chromium } from "playwright";

const server = new Server({ name: "browser", version: "1.0.0" });

let browser = null;
let page = null;

// Define tools...
server.setRequestHandler("tools/list", async () => ({
  tools: [
    { name: "launch", description: "Launch browser", inputSchema: {...} },
    { name: "navigate", description: "Go to URL", inputSchema: {...} },
    { name: "screenshot", description: "Capture viewport", inputSchema: {...} },
    // ...
  ]
}));

// Implement tools...
server.setRequestHandler("tools/call", async (request) => {
  // Handle each tool
});

server.listen();
```

### Package.json

```json
{
  "name": "mcp-browser",
  "version": "1.0.0",
  "type": "module",
  "bin": "./dist/index.js",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^0.5.0",
    "playwright": "^1.40.0"
  }
}
```

See full implementation example in the main workflow file or MCP SDK docs.

---

## Security Notes

- Browser MCP runs locally, no data sent externally
- Screenshots stay on your machine (unless you share them)
- Dev server should only bind to localhost
- Don't commit screenshots to git (add to `.gitignore`)

```bash
# Add to .gitignore
screenshots/
*.png
```

---

## Token/Cost Estimation

Visual QA workflow file: ~600 lines, ~16K chars, ~4K tokens

Per screen iteration:
- Agent analysis: ~500 tokens
- Screenshot (if returned as base64): Large, but processed by MCP
- Comparison report: ~300 tokens

**Tip:** For many screens, autonomous workflow is more cost-effective than manual due to fewer human round-trips.
