export const SmartReadOnlyAnalyzer = async ({ client }) => {
  console.log('✅ SmartReadOnlyAnalyzer plugin loaded!');

  const readOnlyPatterns = {
    // Basic system commands
    simple: ['ls', 'cat', 'grep', 'find', 'head', 'tail', 'less', 'more',
      'wc', 'pwd', 'echo', 'which', 'whereis', 'man', 'tree', 'file', 'stat',
      'du', 'df', 'whoami', 'printenv', 'env', 'type', 'command'],

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
    const firstWord = cmd.trim().split(/\s+/)[0];
    if (readOnlyPatterns.simple.includes(firstWord)) return true;

    for (const [key, pattern] of Object.entries(readOnlyPatterns)) {
      if (key === 'simple') continue;
      if (pattern.test(cmd)) return true;
    }

    return false;
  };

  const isDangerous = (cmd) => {
    return dangerousPatterns.some(pattern => pattern.test(cmd));
  };

  const analyzeWithAI = async (command) => {
    try {
      const response = await client.chat.create({
        messages: [{
          role: "user",
          content: `Analyze this bash command and determine if it's read-only (no modifications to filesystem, system, processes, databases, or remote resources).

Command: ${command}

Consider these frameworks:
- Python/Django: pytest, mypy, show_urls are safe; migrate, pip install are not
- Node/React/Next: npm test, jest, eslint are safe; npm install, next build are not
- Ruby/Rails: rspec, rails routes are safe; rails db:migrate, gem install are not
- PHP/Laravel: phpunit, route:list are safe; artisan migrate, composer install are not
- Commands with pipes, grep, head are usually safe if base command is safe

Respond ONLY with JSON (no markdown):
{
  "isReadOnly": boolean,
  "isDangerous": boolean,
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}`
        }],
        temperature: 0,
        max_tokens: 300
      });

      const text = response.content[0].text.trim();
      const cleanText = text.replace(/```json\n?/g, '').replace(/```\n?/g, '');
      return JSON.parse(cleanText);
    } catch (error) {
      console.error('AI analysis failed:', error);
      return { isReadOnly: false, isDangerous: false, confidence: 0, reason: 'Analysis failed' };
    }
  };

  return {
    "permission.ask": async ({ request }) => {
      if (request.tool !== "bash") {
        return { status: "ask" };
      }

      const command = request.command?.trim();
      if (!command) return { status: "ask" };

      // Fast path: known read-only
      if (isReadOnly(command)) {
        console.log(`✅ Auto-approved (pattern): ${command}`);
        return { status: "allow" };
      }

      // Fast path: known dangerous
      if (isDangerous(command)) {
        console.log(`🚫 Blocked (pattern): ${command}`);
        return { status: "deny" };
      }

      // Slow path: AI analysis
      console.log(`🤔 Analyzing with AI: ${command}`);
      const analysis = await analyzeWithAI(command);

      if (analysis.isReadOnly && analysis.confidence > 0.80) {
        console.log(`🤖 AI Auto-approved: ${command}`);
        console.log(`   Reason: ${analysis.reason}`);
        console.log(`   Confidence: ${(analysis.confidence * 100).toFixed(0)}%`);
        return { status: "allow" };
      } else if (analysis.isDangerous && analysis.confidence > 0.85) {
        console.log(`🚫 AI Blocked: ${command}`);
        console.log(`   Reason: ${analysis.reason}`);
        return { status: "deny" };
      }

      console.log(`❓ AI uncertain (${(analysis.confidence * 100).toFixed(0)}%), asking user`);
      return { status: "ask" };
    }
  };
};
