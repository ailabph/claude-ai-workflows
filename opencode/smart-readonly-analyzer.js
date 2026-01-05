export const SmartReadOnlyAnalyzer = async ({ client }) => {
  console.log('✅ SmartReadOnlyAnalyzer plugin loaded!');

  // Sensitive file patterns - curated list of credential-bearing paths
  const sensitivePathPatterns = [
    /\.env($|\..*)/i,                    // .env, .env.local, .env.production, etc.
    /\.ssh\//,                           // SSH keys
    /\.aws\//,                           // AWS credentials
    /\.git\/config$/,                    // Git config (may have tokens)
    /\.npmrc$/,                          // NPM auth tokens
    /\.pypirc$/,                         // PyPI credentials
    /\.netrc$/,                          // Network credentials
    /\.docker\/config\.json$/,           // Docker auth
    /credentials\.json$/,                // Generic credentials
    /secrets?\.(json|ya?ml|toml)$/i,     // Secrets files
    /\.kube\/config$/,                   // Kubernetes config
    /\.gnupg\//,                         // GPG keys
    /id_rsa|id_ed25519|id_ecdsa/,        // SSH private keys
    /\.pem$/,                            // Certificates/keys
    /\.key$/,                            // Key files
    /password|passwd|token|api[_-]?key/i, // Files with sensitive names
  ];

  // Shell operators that warrant user review
  const shellOperatorPatterns = [
    /\|{1,2}/,                           // | or ||
    /&&/,                                // &&
    />\s*/,                              // > redirect
    />>/,                                // >> append
    /\$\(/,                              // $() subshell
    /`[^`]+`/,                           // backtick subshell
    /;\s*\S/,                            // ; command chaining
  ];

  const readOnlyPatterns = {
    // Basic system commands (note: find excluded - has destructive flags)
    simple: ['ls', 'cat', 'grep', 'head', 'tail', 'less', 'more',
      'wc', 'pwd', 'echo', 'which', 'whereis', 'man', 'tree', 'file', 'stat',
      'du', 'df', 'whoami', 'printenv', 'env', 'type', 'command',
      // Text processing
      'awk', 'cut', 'sort', 'uniq', 'tr', 'column', 'nl', 'tac', 'rev', 'paste', 'join',
      // File inspection
      'od', 'hexdump', 'hd', 'xxd', 'strings', 'diff', 'comm', 'cmp', 'patch',
      // Checksums
      'md5sum', 'sha1sum', 'sha256sum', 'sha512sum', 'cksum', 'sum',
      // Data processing
      'jq', 'yq', 'xmllint', 'xq',
      // Path utilities
      'dirname', 'basename', 'readlink', 'realpath', 'pathchk',
      // Date/math
      'date', 'cal', 'bc', 'expr', 'seq', 'factor',
      // Decompression to stdout
      'zcat', 'bzcat', 'xzcat', 'zless', 'bzless', 'xzless',
      // Encoding
      'base64', 'base32', 'uuencode', 'uudecode',
      // Network read-only
      'ping', 'traceroute', 'nslookup', 'dig', 'host', 'whois', 'ifconfig', 'ip',
      // Process inspection
      'ps', 'top', 'htop', 'pgrep', 'lsof', 'netstat', 'ss',
      // Misc
      'yes', 'true', 'false', 'sleep', 'watch', 'tee', 'xargs'],

    // sed is only safe without -i (in-place edit)
    sedSafe: /^sed\s+(?!.*-i)/,

    // find is only safe without destructive/write actions
    findSafe: /^find\s+(?!.*(-delete|-exec|-execdir|-ok|-okdir|-fprint|-fprint0|-fprintf|-fls))/,

    // Git read-only
    git: /^git\s+(status|log|diff|show|branch|remote(\s+-v)?|config\s+--get|rev-parse|describe|tag|ls-files|ls-remote|shortlog|blame|reflog|cherry)(\s|$)/,

    // Python testing
    pythonTest: /^python\s+(-m\s+)?(pytest|unittest|nose2|tox)(\s|$)/,
    pythonTestDirect: /^(pytest|tox)(\s|$)/,

    // Python linting
    pythonLint: /^python\s+(-m\s+)?(mypy|pylint|flake8|bandit|pyright|ruff\s+check|vulture)(\s|$)/,
    pythonLintDirect: /^(mypy|pylint|flake8|bandit|pyright|ruff\s+check)(\s|$)/,

    // Python coverage
    pythonCoverage: /^(coverage\s+(report|html|xml|json)|python\s+-m\s+coverage\s+(report|html|xml|json))(\s|$)/,

    // Python formatters (check mode)
    pythonFormatCheck: /^(black\s+--check|isort\s+--check|autopep8\s+--diff|yapf\s+--diff)(\s|$)/,

    // Python security
    pythonSecurity: /^(safety\s+check|bandit|pip-audit)(\s|$)/,

    // Django
    django: /^python\s+manage\.py\s+(show_urls|showmigrations|check|inspectdb|diffsettings|sqlmigrate|sqlsequencereset|validate|testserver|describe_form|list_signals|graph_models|print_settings|show_template_tags|dumpdata\s+--natural-foreign|test|--help|-h)(\s|$|\|)/,
    djangoPlan: /^python\s+manage\.py\s+migrate\s+--plan/,

    // Flask
    flask: /^flask\s+(routes|--help|-h)(\s|$)/,

    // Node.js package managers
    npm: /^(npm|yarn|pnpm)\s+(test|run\s+(test|lint|check|typecheck|type-check|validate):|outdated|list|ls|view|info|search|audit|why|explain)(\s|$)/,

    // Node.js test runners
    nodeTest: /^(jest|vitest|mocha|ava|tap|tape|jasmine|karma)(\s|--|$)/,

    // Next.js
    nextjs: /^(next|npx\s+next|npm\s+run\s+next|yarn\s+next|pnpm\s+next)\s+(lint|info|telemetry\s+status)(\s|$)/,
    nextjsDebug: /^(next|npx\s+next)\s+build.*--debug/,

    // React
    react: /^(react-scripts|npm\s+run\s+react-scripts)\s+test(\s|$)/,

    // Vue
    vue: /^(vue|npx\s+@?vue\/cli-service)\s+(lint|test|info|inspect)(\s|$)/,

    // Angular
    angular: /^(ng|npx\s+ng)\s+(lint|test|e2e|version|config|analytics\s+info)(\s|$)/,

    // NestJS
    nestjs: /^(nest|npx\s+@nestjs\/cli)\s+(info|--help|-h)(\s|$)/,
    nestjsTest: /^(npm|yarn|pnpm)\s+run\s+(test|test:|e2e)/,

    // Svelte/SvelteKit
    svelte: /^(svelte-kit|vite)\s+(check|sync)(\s|$)/,

    // Ruby/Rails
    rails: /^(rails|bundle\s+exec\s+rails)\s+(routes|db:migrate:status|about|stats|notes|time:zones|middleware|console\s+--sandbox)(\s|$)/,
    rspec: /^(rspec|bundle\s+exec\s+rspec)(\s|$)/,
    rubocop: /^(rubocop|bundle\s+exec\s+rubocop)(\s|$)/,

    // PHP/Laravel
    laravel: /^php\s+artisan\s+(route:list|route:cache|config:show|env|inspire|list|help|about|schedule:list|event:list|test)(\s|$)/,
    phpcs: /^(phpcs|vendor\/bin\/phpcs)(\s|$)/,
    phpunit: /^(phpunit|vendor\/bin\/phpunit|php\s+artisan\s+test)(\s|$)/,

    // Symfony
    symfony: /^(php\s+bin\/console|symfony\s+console)\s+(debug:|list|about|router:match)(\s|$)/,

    // Rust
    cargo: /^cargo\s+(check|clippy|test|bench|doc|tree|search|metadata|verify-project)(\s|$)/,
    rustfmt: /^(rustfmt\s+--check|cargo\s+fmt\s+--\s+--check)(\s|$)/,

    // Go
    golang: /^go\s+(test|vet|list|version|env|mod\s+(graph|verify|why)|fmt\s+-n)(\s|$)/,

    // Java
    maven: /^mvn\s+(test|verify|validate|dependency:tree|dependency:analyze|help:|--version)(\s|$)/,
    gradle: /^(gradle|\.\/gradlew)\s+(test|check|dependencies|tasks|properties|--version)(\s|$)/,

    // Linters
    linters: /^(eslint|tslint|prettier\s+--check|stylelint|htmlhint|csslint|jshint|standard|xo)(\s|$)/,

    // Type checkers
    typecheck: /^(tsc\s+(--noEmit|--build\s+--dry)|flow\s+check|mypy|pyright)(\s|$)/,

    // Build tools (safe modes)
    buildSafe: /^(webpack\s+--json|vite\s+preview|rollup\s+--config\s+--silent)(\s|$)/,

    // Make
    make: /^make\s+(test|check|lint|verify|validate|help)(\s|$)/,

    // GitHub CLI
    gh: /^gh\s+(repo|issue|pr|run|workflow|release|gist)\s+(view|list|status|diff)(\s|$)/,
    ghApi: /^gh\s+api\s+GET(\s|$)/,

    // AWS CLI
    aws: /^aws\s+\w+\s+(describe-|list-|get-)(\s|$)/,
    awsS3: /^aws\s+s3\s+ls(\s|$)/,

    // Docker
    docker: /^docker\s+(ps|images|inspect|logs|version|info|stats|top|history)(\s|$)/,

    // Kubernetes
    kubectl: /^kubectl\s+(get|describe|logs|explain|api-resources|api-versions|cluster-info|top|diff)(\s|$)/,

    // Terraform
    terraform: /^terraform\s+(show|plan|validate|output|state\s+(list|show)|providers|version|fmt\s+-check)(\s|$)/,

    // Archive tools (read-only operations)
    tar: /^tar\s+(-t|--list)/,
    unzip: /^unzip\s+-l/,
    zip: /^zip\s+-sf/,
    gzip: /^(gzip\s+-[cdlt]|gunzip|gzcat)/,
    bzip2: /^(bzip2\s+-[cdt]|bunzip2)/,
    xz: /^(xz\s+-[cdlt]|unxz)/,

    // curl (safe read operations - GET by default, or explicit -X GET)
    curl: /^curl\s+(?!.*(-X\s+(POST|PUT|DELETE|PATCH)|--request\s+(POST|PUT|DELETE|PATCH)))/,

    // wget (safe when outputting to stdout or just checking)
    wget: /^wget\s+(--spider|-O\s+-|--output-document=-)/,

    // grep variants (rg = ripgrep, ag = silver searcher)
    grepVariants: /^(rg|ripgrep|ag|ack|ack-grep)\s/,
  };

  const dangerousPatterns = [
    // System
    /^(rm|sudo|mv|dd|mkfs|fdisk|shutdown|reboot|kill|pkill)(\s|$)/,

    // Git
    /git\s+(push|force|reset\s+--hard|clean\s+-fd|rebase|merge)/,

    // GitHub
    /^gh\s+(repo|issue|pr|release)\s+(create|delete|edit|merge|close)(\s|$)/,
    /^gh\s+api\s+(POST|PUT|PATCH|DELETE)(\s|$)/,

    // AWS
    /^aws\s+\w+\s+(delete-|terminate-|remove-|destroy-|put-|create-)(\s|$)/,
    /^aws\s+s3\s+(rm|sync.*--delete|cp.*--recursive)/,

    // Docker
    /^docker\s+(rm|rmi|stop|kill|prune|build|push)(\s|$)/,

    // Kubernetes
    /^kubectl\s+(delete|apply|create|replace|patch|scale|rollout)(\s|$)/,

    // File redirection
    />\s*\/(\s|$)/,

    // Package installation
    /^(pip|npm|yarn|pnpm|apt|apt-get|brew|cargo|gem)\s+install(\s|$)/,
    /^python\s+(-m\s+)?pip\s+install(\s|$)/,

    // Formatters (write mode)
    /^black\s+(?!--check)/,
    /^(isort|autopep8|yapf)\s+(?!--(check|diff))/,
    /^prettier\s+--write(\s|$)/,

    // Django dangerous
    /^python\s+manage\.py\s+(migrate(?!\s+--plan)|makemigrations|loaddata|flush|createsuperuser|collectstatic|compilemessages|sqlflush)(\s|$)/,

    // Database
    /^(psql|mysql|sqlite3).*-c.*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE)/i,
  ];

  const isReadOnly = (cmd) => {
    const trimmed = cmd.trim();
    const firstWord = trimmed.split(/\s+/)[0];
    if (readOnlyPatterns.simple.includes(firstWord)) return true;

    for (const [key, pattern] of Object.entries(readOnlyPatterns)) {
      if (key === 'simple') continue;
      if (pattern.test(trimmed)) return true;
    }

    return false;
  };

  // Parse command into pipeline segments, respecting quotes
  const parsePipeline = (cmd) => {
    const segments = [];
    let current = '';
    let inQuote = null;
    let escaped = false;

    for (let i = 0; i < cmd.length; i++) {
      const char = cmd[i];

      if (escaped) {
        current += char;
        escaped = false;
        continue;
      }

      if (char === '\\') {
        escaped = true;
        current += char;
        continue;
      }

      if ((char === '"' || char === "'") && !inQuote) {
        inQuote = char;
        current += char;
        continue;
      }

      if (char === inQuote) {
        inQuote = null;
        current += char;
        continue;
      }

      if (char === '|' && !inQuote) {
        // Check if it's || (OR operator) - this needs special handling
        if (cmd[i + 1] === '|') {
          current += '||';
          i++; // skip next |
          continue;
        }
        // It's a pipe - save current segment
        if (current.trim()) {
          segments.push(current.trim());
        }
        current = '';
        continue;
      }

      current += char;
    }

    // Add final segment
    if (current.trim()) {
      segments.push(current.trim());
    }

    return segments;
  };

  // Check if all commands in a pipeline are read-only
  const isPipelineReadOnly = (cmd) => {
    const segments = parsePipeline(cmd);

    // If no pipe found, return null (let normal checks handle it)
    if (segments.length <= 1) {
      return null;
    }

    // Check each segment
    for (const segment of segments) {
      if (!isReadOnly(segment)) {
        return false;
      }
    }

    return true;
  };

  const isDangerous = (cmd) => {
    return dangerousPatterns.some(pattern => pattern.test(cmd));
  };

  // Check if command contains shell operators that warrant review
  const hasShellOperators = (cmd) => {
    return shellOperatorPatterns.some(pattern => pattern.test(cmd));
  };

  // Bare sensitive filenames that should be detected without path prefix
  const bareSensitiveFilenames = [
    'credentials.json', 'secrets.json', 'secrets.yaml', 'secrets.yml', 'secrets.toml',
    'id_rsa', 'id_ed25519', 'id_ecdsa', 'id_dsa',
    '.env', '.npmrc', '.pypirc', '.netrc',
  ];

  // Extract file paths and potential sensitive tokens from command
  const extractPaths = (cmd) => {
    const paths = new Set();
    // Quoted paths
    const quotedMatches = cmd.match(/["']([^"']+)["']/g) || [];
    quotedMatches.forEach(m => paths.add(m.replace(/["']/g, '')));
    // Unquoted tokens: paths (contain /), dotfiles (start with .), or files with extensions
    const words = cmd.split(/\s+/);
    words.forEach(w => {
      if (w.startsWith('-')) return; // skip flags
      if (w.includes('/') || w.startsWith('.')) {
        paths.add(w);
      }
      // Also check bare filenames with extensions that might be sensitive
      if (w.includes('.') && !w.startsWith('-')) {
        paths.add(w);
      }
      // Check known bare sensitive filenames
      if (bareSensitiveFilenames.includes(w)) {
        paths.add(w);
      }
    });
    return Array.from(paths);
  };

  // Check if command targets sensitive files
  const targetsSensitiveFiles = (cmd) => {
    const paths = extractPaths(cmd);
    const matches = paths.filter(p => sensitivePathPatterns.some(pattern => pattern.test(p)));
    // Also check for bare sensitive filenames directly in command
    bareSensitiveFilenames.forEach(filename => {
      if (cmd.includes(filename) && !matches.some(m => m.includes(filename))) {
        matches.push(filename);
      }
    });
    return matches;
  };

  // Check if grep/rg command is in "safe" mode (files-only or count)
  const isGrepSafeMode = (cmd) => {
    const firstWord = cmd.trim().split(/\s+/)[0];
    if (!['grep', 'rg', 'ripgrep', 'ag', 'ack'].includes(firstWord)) return false;
    // Safe modes: -l (files only), -c/--count, --files-with-matches
    return /\s(-l|--files-with-matches|-c|--count)\b/.test(cmd);
  };

  // Patterns for inline secrets that should be redacted
  const inlineSecretPatterns = [
    // Flags with values: --token=xxx, --password xxx, -p xxx
    /(--(token|password|secret|api[_-]?key|auth|credential|private[_-]?key))[=\s]+\S+/gi,
    /(-(p|k|t)\s+)\S+/g, // common short flags for password/key/token
    // Environment variable assignments with sensitive names
    /(AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|GITHUB_TOKEN|API_KEY|AUTH_TOKEN|PASSWORD|SECRET)[=]\S+/gi,
    // Authorization headers
    /(Authorization:\s*)(Bearer\s+)?\S+/gi,
    // Base64-ish tokens (require = or + or / to distinguish from git SHAs and filenames)
    // This avoids redacting 40-char hex git SHAs or long filenames
    /\b[A-Za-z0-9_-]{32,}={1,2}\b/g,  // base64 with padding (ends in = or ==)
    /\b(?=[A-Za-z0-9+/]*[+/])[A-Za-z0-9+/]{32,}\b/g,  // 32+ chars with at least one + or /
  ];

  // Redact sensitive content in command for logging and AI
  const redactCommand = (cmd) => {
    let redacted = cmd;

    // Redact sensitive file paths
    const sensitivePaths = targetsSensitiveFiles(cmd);
    sensitivePaths.forEach(path => {
      const parts = path.split('/');
      const filename = parts[parts.length - 1];
      redacted = redacted.replace(path, `[REDACTED:${filename}]`);
    });

    // Redact inline secrets
    inlineSecretPatterns.forEach(pattern => {
      redacted = redacted.replace(pattern, (match, prefix) => {
        // Keep the flag/key name, redact the value
        if (prefix) return `${prefix}[REDACTED]`;
        return '[REDACTED]';
      });
    });

    return redacted;
  };

  // AI analysis receives redacted command to avoid sending secrets upstream
  const analyzeWithAI = async (redactedCommand) => {
    try {
      const response = await client.chat.create({
        messages: [{
          role: "user",
          content: `Analyze this bash command and determine if it should be auto-approved or require user confirmation.

Command: ${redactedCommand}

Auto-approve criteria:
- No destructive operations (delete, overwrite, force-push, etc.)
- No package installations or system-wide modifications
- No credential exposure risk
- No writes outside workspace (system files, home dir config, etc.)
- Workspace-local writes are OK (caches, build artifacts, test outputs, .pyc files)

Framework examples:
- SAFE: pytest, mypy, eslint, rspec, phpunit, cargo test, go test, rails routes, npm test, tsc, coverage
- NEEDS REVIEW: pip install, npm install, migrate, deploy, push, rm, mv, chmod, chown

Respond ONLY with JSON (no markdown):
{
  "shouldAutoApprove": boolean,
  "riskLevel": "none" | "low" | "medium" | "high",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "riskFlags": ["list", "of", "concerns"]
}`
        }],
        temperature: 0,
        max_tokens: 300
      });

      const text = response.content[0].text.trim();
      const cleanText = text.replace(/```json\n?/g, '').replace(/```\n?/g, '');
      const result = JSON.parse(cleanText);
      // Map new schema to existing code expectations
      return {
        isReadOnly: result.shouldAutoApprove,
        isDangerous: result.riskLevel === 'high',
        confidence: result.confidence,
        reason: result.reason,
        riskFlags: result.riskFlags || [],
      };
    } catch (error) {
      console.error('AI analysis failed:', error);
      return { isReadOnly: false, isDangerous: false, confidence: 0, reason: 'Analysis failed', riskFlags: [] };
    }
  };

  return {
    "permission.ask": async (args) => {
      // Handle multiple payload shapes from different runtimes
      // Could be: { request: { tool, command } } or { tool, command } or { tool_input: { command } }
      // Also handle undefined/null args to prevent crashes
      const request = args?.request ?? args ?? {};
      const tool = request?.tool ?? request?.tool_name;
      const command = (
        request?.command ??
        request?.tool_input?.command ??
        request?.input?.command ??
        request?.args?.command
      )?.trim();

      // Only process bash commands
      if (tool !== "bash" && tool !== "Bash") {
        return { status: "ask" };
      }

      if (!command) {
        console.log(`⚠️ No command found in request, asking user`);
        return { status: "ask" };
      }

      const redacted = redactCommand(command);
      const sensitivePaths = targetsSensitiveFiles(command);
      const hasSensitiveTargets = sensitivePaths.length > 0;

      // Check for sensitive file access
      if (hasSensitiveTargets) {
        // Note: both cases ask, but we differentiate in logging for context
        if (isGrepSafeMode(command)) {
          console.log(`⚠️ Asking (sensitive file, grep safe mode): ${redacted}`);
          console.log(`   Reason: Searching sensitive paths (files-only/count mode - lower risk)`);
          return { status: "ask" };
        }
        // Full content access to sensitive files - always ask
        console.log(`⚠️ Asking (sensitive file read): ${redacted}`);
        console.log(`   Reason: Command accesses credential-bearing files: ${sensitivePaths.map(p => p.split('/').pop()).join(', ')}`);
        return { status: "ask" };
      }

      // Check for shell operators (pipes, redirects, subshells)
      if (hasShellOperators(command)) {
        // Special case: if it's ONLY a pipe (|) and all pipeline segments are read-only, auto-approve
        const hasPipe = /\|(?!\|)/.test(command); // single pipe, not ||
        const hasOtherOperators = /(\|\||&&|>>?|\$\(|`[^`]+`|;\s*\S)/.test(command);

        if (hasPipe && !hasOtherOperators) {
          const pipelineCheck = isPipelineReadOnly(command);
          if (pipelineCheck === true) {
            console.log(`✅ Auto-approved (read-only pipeline): ${redacted}`);
            return { status: "allow" };
          } else if (pipelineCheck === false) {
            console.log(`⚠️ Asking (pipeline contains non-read-only command): ${redacted}`);
            console.log(`   Reason: One or more commands in the pipeline may modify state`);
            return { status: "ask" };
          }
        }

        // Other operators (||, &&, >, $(), etc.) or mixed operators - always ask
        console.log(`⚠️ Asking (shell operators detected): ${redacted}`);
        console.log(`   Reason: Command contains redirects, subshells, or control operators - requires review`);
        return { status: "ask" };
      }

      // Fast path: known read-only
      if (isReadOnly(command)) {
        console.log(`✅ Auto-approved (pattern): ${redacted}`);
        return { status: "allow" };
      }

      // Known dangerous patterns - ask instead of deny
      if (isDangerous(command)) {
        console.log(`⚠️ Asking (dangerous pattern): ${redacted}`);
        console.log(`   Reason: Command matches dangerous pattern (destructive/mutating operation)`);
        return { status: "ask" };
      }

      // Slow path: AI analysis (use redacted command to avoid sending secrets upstream)
      console.log(`🤔 Analyzing with AI: ${redacted}`);
      const analysis = await analyzeWithAI(redacted);

      if (analysis.isReadOnly && analysis.confidence > 0.80) {
        console.log(`🤖 AI Auto-approved: ${redacted}`);
        console.log(`   Reason: ${analysis.reason}`);
        console.log(`   Confidence: ${(analysis.confidence * 100).toFixed(0)}%`);
        return { status: "allow" };
      }

      // For dangerous or uncertain commands, ask with explanation
      if (analysis.isDangerous) {
        console.log(`⚠️ Asking (AI flagged as dangerous): ${redacted}`);
        console.log(`   Reason: ${analysis.reason}`);
        return { status: "ask" };
      }

      console.log(`⚠️ Asking (AI uncertain, ${(analysis.confidence * 100).toFixed(0)}%): ${redacted}`);
      console.log(`   Reason: ${analysis.reason || 'Could not determine if command is read-only'}`);
      return { status: "ask" };
    }
  };
};
