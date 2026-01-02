#!/bin/bash

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then exit 0; fi

# Set to true for debugging
DEBUG=false

debug_log() {
if [ "$DEBUG" = true ]; then
echo "🔍 DEBUG: $1" >&2
fi
}

is_readonly_command() {
    local cmd="$1"

# ============================================
# BASIC SYSTEM COMMANDS
# ============================================
if echo "$cmd" | grep -qE '^(ls|cat|grep|find|head|tail|less|more|wc|pwd|echo|which|whereis|man|tree|file|stat|du|df|whoami|printenv|env|type|command)(\s|$)'; then
debug_log "Matched basic system command"
return 0
fi

# ============================================
# GIT COMMANDS (READ-ONLY)
# ============================================
if echo "$cmd" | grep -qE '^git\s+(status|log|diff|show|branch|remote(\s+-v)?|config\s+--get|rev-parse|describe|tag|ls-files|ls-remote|shortlog|blame|reflog|cherry)(\s|$)'; then
debug_log "Matched git read-only"
return 0
fi

# ============================================
# PYTHON - TESTING & ANALYSIS
# ============================================

# Pytest and test runners
if echo "$cmd" | grep -qE '^python\s+(-m\s+)?(pytest|unittest|nose2|tox)(\s|$)'; then
debug_log "Matched Python test runner"
return 0
fi
if echo "$cmd" | grep -qE '^(pytest|tox)(\s|$)'; then
debug_log "Matched direct test command"
return 0
fi

# Linters and type checkers
if echo "$cmd" | grep -qE '^python\s+(-m\s+)?(mypy|pylint|flake8|bandit|pyright|ruff\s+check|vulture)(\s|$)'; then
debug_log "Matched Python linter/type checker"
return 0
fi
if echo "$cmd" | grep -qE '^(mypy|pylint|flake8|bandit|pyright|ruff\s+check)(\s|$)'; then
debug_log "Matched direct linter command"
return 0
fi

# Code coverage (read-only reports)
if echo "$cmd" | grep -qE '^(coverage\s+(report|html|xml|json)|python\s+-m\s+coverage\s+(report|html|xml|json))(\s|$)'; then
debug_log "Matched coverage report"
return 0
fi

# Formatters in CHECK mode only
if echo "$cmd" | grep -qE '^(black\s+--check|isort\s+--check|autopep8\s+--diff|yapf\s+--diff)(\s|$)'; then
debug_log "Matched formatter in check mode"
return 0
fi

# Security scanners
if echo "$cmd" | grep -qE '^(safety\s+check|bandit|pip-audit)(\s|$)'; then
debug_log "Matched security scanner"
return 0
fi

# Python -c with print only (safe pattern)
if echo "$cmd" | grep -qE '^python\s+-c\s+"[^"]*print\(' && \
        ! echo "$cmd" | grep -qE '(os\.|subprocess\.|open\([^)]*[,\s]*["\x27]w|exec\(|eval\(|__import__\(["\x27]os|shutil\.)'; then
debug_log "Matched safe python -c print"
return 0
fi

# ============================================
# DJANGO COMMANDS
# ============================================

# Read-only Django management commands
if echo "$cmd" | grep -qE '^python\s+manage\.py\s+(show_urls|showmigrations|check|inspectdb|diffsettings|sqlmigrate|sqlsequencereset|validate|testserver|describe_form|list_signals|graph_models|print_settings|print_user_for_session|show_template_tags|show_urls|dumpdata\s+--natural-foreign|--help|-h)(\s|$|\|)'; then
debug_log "Matched Django read-only command"
return 0
fi

# Django migrate in plan mode (read-only)
if echo "$cmd" | grep -qE '^python\s+manage\.py\s+migrate\s+--plan'; then
debug_log "Matched Django migrate --plan"
return 0
fi

# Django test command (read-only)
if echo "$cmd" | grep -qE '^python\s+manage\.py\s+test(\s|$)'; then
debug_log "Matched Django test"
return 0
fi

# ============================================
# FLASK COMMANDS
# ============================================

if echo "$cmd" | grep -qE '^flask\s+(routes|--help|-h)(\s|$)'; then
debug_log "Matched Flask read-only command"
return 0
fi

# ============================================
# NODE.JS / NPM / YARN / PNPM
# ============================================

# Package manager read-only commands
if echo "$cmd" | grep -qE '^(npm|yarn|pnpm)\s+(test|run\s+test|run\s+test:|run\s+lint|run\s+lint:|run\s+check|run\s+check:|run\s+typecheck|run\s+type-check|run\s+validate|outdated|list|ls|view|info|search|audit|why|explain)(\s|$)'; then
debug_log "Matched npm/yarn/pnpm read-only"
return 0
fi

# Direct test runners
if echo "$cmd" | grep -qE '^(jest|vitest|mocha|ava|tap|tape|jasmine|karma)(\s|--|$)'; then
debug_log "Matched Node test runner"
return 0
fi

# ============================================
# NEXT.JS COMMANDS
# ============================================

# Next.js read-only commands
if echo "$cmd" | grep -qE '^(next|npx\s+next|npm\s+run\s+next|yarn\s+next|pnpm\s+next)\s+(lint|info|telemetry\s+status)(\s|$)'; then
debug_log "Matched Next.js read-only"
return 0
fi

# Next.js build in development/check mode
if echo "$cmd" | grep -qE '^(next|npx\s+next)\s+build.*--debug'; then
debug_log "Matched Next.js debug build"
return 0
fi

# ============================================
# REACT / CREATE-REACT-APP
# ============================================

# React Scripts test
if echo "$cmd" | grep -qE '^(react-scripts|npm\s+run\s+react-scripts)\s+test(\s|$)'; then
debug_log "Matched React test"
return 0
fi

# ============================================
# VUE.JS COMMANDS
# ============================================

# Vue CLI read-only
if echo "$cmd" | grep -qE '^(vue|npx\s+@?vue/cli-service)\s+(lint|test|info|inspect)(\s|$)'; then
debug_log "Matched Vue read-only"
return 0
fi

# ============================================
# ANGULAR COMMANDS
# ============================================

# Angular CLI read-only
if echo "$cmd" | grep -qE '^(ng|npx\s+ng)\s+(lint|test|e2e|version|config|analytics\s+info)(\s|$)'; then
debug_log "Matched Angular read-only"
return 0
fi

# ============================================
# NESTJS COMMANDS
# ============================================

# NestJS CLI read-only
if echo "$cmd" | grep -qE '^(nest|npx\s+@nestjs/cli)\s+(info|--help|-h)(\s|$)'; then
debug_log "Matched NestJS read-only"
return 0
fi

# NestJS test
if echo "$cmd" | grep -qE '^(npm|yarn|pnpm)\s+run\s+(test|test:|e2e)'; then
debug_log "Matched NestJS test"
return 0
fi

# ============================================
# SVELTE / SVELTEKIT
# ============================================

if echo "$cmd" | grep -qE '^(svelte-kit|vite)\s+(check|sync)(\s|$)'; then
debug_log "Matched Svelte read-only"
return 0
fi

# ============================================
# RUBY / RAILS
# ============================================

# Rails read-only commands
if echo "$cmd" | grep -qE '^(rails|bundle\s+exec\s+rails)\s+(routes|db:migrate:status|about|stats|notes|time:zones|middleware|console\s+--sandbox|runner\s+.*puts)(\s|$)'; then
debug_log "Matched Rails read-only"
return 0
fi

# RSpec tests
if echo "$cmd" | grep -qE '^(rspec|bundle\s+exec\s+rspec)(\s|$)'; then
debug_log "Matched RSpec"
return 0
fi

# Rubocop (linter)
if echo "$cmd" | grep -qE '^(rubocop|bundle\s+exec\s+rubocop)(\s|$)'; then
debug_log "Matched Rubocop"
return 0
fi

# ============================================
# PHP / LARAVEL / SYMFONY
# ============================================

# Laravel Artisan read-only
if echo "$cmd" | grep -qE '^php\s+artisan\s+(route:list|route:cache|config:show|env|inspire|list|help|about|schedule:list|event:list|view:cache|vendor:publish\s+--tag)(\s|$)'; then
debug_log "Matched Laravel read-only"
return 0
fi

# PHP CodeSniffer (linter)
if echo "$cmd" | grep -qE '^(phpcs|vendor/bin/phpcs)(\s|$)'; then
debug_log "Matched PHP CodeSniffer"
return 0
fi

# PHPUnit tests
if echo "$cmd" | grep -qE '^(phpunit|vendor/bin/phpunit|php\s+artisan\s+test)(\s|$)'; then
debug_log "Matched PHPUnit"
return 0
fi

# Symfony console read-only
if echo "$cmd" | grep -qE '^(php\s+bin/console|symfony\s+console)\s+(debug:|list|about|router:match)(\s|$)'; then
debug_log "Matched Symfony read-only"
return 0
fi

# ============================================
# RUST / CARGO
# ============================================

if echo "$cmd" | grep -qE '^cargo\s+(check|clippy|test|bench|doc|tree|search|metadata|verify-project)(\s|$)'; then
debug_log "Matched Cargo read-only"
return 0
fi

# Rustfmt in check mode
if echo "$cmd" | grep -qE '^(rustfmt\s+--check|cargo\s+fmt\s+--\s+--check)(\s|$)'; then
debug_log "Matched rustfmt check"
return 0
fi

# ============================================
# GO COMMANDS
# ============================================

if echo "$cmd" | grep -qE '^go\s+(test|vet|list|version|env|mod\s+(graph|verify|why)|fmt\s+-n)(\s|$)'; then
debug_log "Matched Go read-only"
return 0
fi

# ============================================
# JAVA / MAVEN / GRADLE
# ============================================

# Maven
if echo "$cmd" | grep -qE '^mvn\s+(test|verify|validate|dependency:tree|dependency:analyze|help:|--version)(\s|$)'; then
debug_log "Matched Maven read-only"
return 0
fi

# Gradle
if echo "$cmd" | grep -qE '^(gradle|./gradlew)\s+(test|check|dependencies|tasks|properties|--version)(\s|$)'; then
debug_log "Matched Gradle read-only"
return 0
fi

# ============================================
# LINTERS & FORMATTERS (CHECK MODE)
# ============================================

if echo "$cmd" | grep -qE '^(eslint|tslint|prettier\s+--check|stylelint|htmlhint|csslint|jshint|standard|xo)(\s|$)'; then
debug_log "Matched linter"
return 0
fi

# ============================================
# TYPE CHECKERS
# ============================================

if echo "$cmd" | grep -qE '^(tsc\s+(--noEmit|--build\s+--dry)|flow\s+check|mypy|pyright)(\s|$)'; then
debug_log "Matched type checker"
return 0
fi

# ============================================
# BUILD TOOLS (CHECK/DRY-RUN MODE)
# ============================================

if echo "$cmd" | grep -qE '^(webpack\s+--json|vite\s+preview|rollup\s+--config\s+--silent)(\s|$)'; then
debug_log "Matched build tool in safe mode"
return 0
fi

# ============================================
# MAKE (SPECIFIC SAFE TARGETS)
# ============================================

if echo "$cmd" | grep -qE '^make\s+(test|check|lint|verify|validate|help)(\s|$)'; then
debug_log "Matched Make safe target"
return 0
fi

# ============================================
# GITHUB CLI
# ============================================

if echo "$cmd" | grep -qE '^gh\s+(repo|issue|pr|run|workflow|release|gist)\s+(view|list|status|diff)(\s|$)'; then
debug_log "Matched GitHub CLI read-only"
return 0
fi
if echo "$cmd" | grep -qE '^gh\s+api\s+GET(\s|$)'; then
debug_log "Matched GitHub API GET"
return 0
fi

# ============================================
# AWS CLI
# ============================================

if echo "$cmd" | grep -qE '^aws\s+\w+\s+(describe-|list-|get-)(\s|$)'; then
debug_log "Matched AWS describe/list/get"
return 0
fi
if echo "$cmd" | grep -qE '^aws\s+s3\s+ls(\s|$)'; then
debug_log "Matched AWS S3 ls"
return 0
fi

# ============================================
# DOCKER
# ============================================

if echo "$cmd" | grep -qE '^docker\s+(ps|images|inspect|logs|version|info|stats|top|history)(\s|$)'; then
debug_log "Matched Docker read-only"
return 0
fi

# ============================================
# KUBERNETES / KUBECTL
# ============================================

if echo "$cmd" | grep -qE '^kubectl\s+(get|describe|logs|explain|api-resources|api-versions|cluster-info|top|diff)(\s|$)'; then
debug_log "Matched kubectl read-only"
return 0
fi

# ============================================
# TERRAFORM
# ============================================

if echo "$cmd" | grep -qE '^terraform\s+(show|plan|validate|output|state\s+(list|show)|providers|version|fmt\s+-check)(\s|$)'; then
debug_log "Matched Terraform read-only"
return 0
fi

debug_log "No read-only pattern matched"
return 1
}

is_dangerous_command() {
local cmd="$1"

# System commands
if echo "$cmd" | grep -qE '^(rm|sudo|mv|dd|mkfs|fdisk|shutdown|reboot|kill|pkill)(\s|$)'; then
debug_log "Matched dangerous system command"
return 0
fi

# Git dangerous
if echo "$cmd" | grep -qE 'git\s+(push|force|reset\s+--hard|clean\s+-fd|rebase|merge)'; then
debug_log "Matched dangerous git"
return 0
fi

# GitHub CLI write
if echo "$cmd" | grep -qE '^gh\s+(repo|issue|pr|release)\s+(create|delete|edit|merge|close)(\s|$)'; then
debug_log "Matched GitHub write"
return 0
fi
if echo "$cmd" | grep -qE '^gh\s+api\s+(POST|PUT|PATCH|DELETE)(\s|$)'; then
debug_log "Matched GitHub API write"
return 0
fi

# AWS dangerous
if echo "$cmd" | grep -qE '^aws\s+\w+\s+(delete-|terminate-|remove-|destroy-|put-|create-)(\s|$)'; then
debug_log "Matched AWS dangerous"
return 0
fi
if echo "$cmd" | grep -qE '^aws\s+s3\s+(rm|sync.*--delete|cp.*--recursive)'; then
debug_log "Matched AWS S3 dangerous"
return 0
fi

# Docker dangerous
if echo "$cmd" | grep -qE '^docker\s+(rm|rmi|stop|kill|prune|build|push)(\s|$)'; then
debug_log "Matched Docker dangerous"
return 0
fi

# Kubernetes dangerous
if echo "$cmd" | grep -qE '^kubectl\s+(delete|apply|create|replace|patch|scale|rollout)(\s|$)'; then
debug_log "Matched kubectl dangerous"
return 0
fi

# File redirection to system paths
if echo "$cmd" | grep -qE '>\s*/(\s|$)'; then
debug_log "Matched system path redirection"
return 0
fi

# Package installation
if echo "$cmd" | grep -qE '^(pip|npm|yarn|pnpm|apt|apt-get|brew|cargo|gem)\s+install(\s|$)'; then
debug_log "Matched package installation"
return 0
fi
if echo "$cmd" | grep -qE '^python\s+(-m\s+)?pip\s+install(\s|$)'; then
debug_log "Matched pip install"
return 0
fi

# Formatters in WRITE mode
if echo "$cmd" | grep -qE '^black\s+(?!--check)'; then
debug_log "Matched black write mode"
return 0
fi
if echo "$cmd" | grep -qE '^(isort|autopep8|yapf)\s+(?!--(check|diff))'; then
debug_log "Matched Python formatter write mode"
return 0
fi
if echo "$cmd" | grep -qE '^prettier\s+--write(\s|$)'; then
debug_log "Matched prettier write mode"
return 0
fi

# Django dangerous
if echo "$cmd" | grep -qE '^python\s+manage\.py\s+(migrate(?!\s+--plan)|makemigrations|loaddata|flush|createsuperuser|collectstatic|compilemessages|changepassword|clearsessions|sqlflush)(\s|$)'; then
debug_log "Matched Django dangerous"
return 0
fi

# Database operations
if echo "$cmd" | grep -qE '^(psql|mysql|sqlite3).*-c.*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE)'; then
debug_log "Matched dangerous SQL"
return 0
fi

debug_log "No dangerous pattern matched"
return 1
}

# Fast path: known read-only
if is_readonly_command "$COMMAND"; then
echo "✅ Pattern match (read-only): $COMMAND" >&2
cat << EOF
{
"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Known read-only command pattern"
}
}
EOF
exit 0
fi

# Fast path: known dangerous
if is_dangerous_command "$COMMAND"; then
echo "🚫 Pattern match (dangerous): $COMMAND" >&2
exit 2
fi

# Slow path: AI analysis
echo "🤔 Uncertain command, using AI: $COMMAND" >&2
debug_log "Entering AI analysis path"

# Check if AI analyzer exists
AI_ANALYZER="$HOME/.claude/hooks/ai-readonly-analyzer.py"
if [ ! -f "$AI_ANALYZER" ]; then
echo "⚠️  AI analyzer not found at: $AI_ANALYZER" >&2
debug_log "AI analyzer file missing, defaulting to ask"
exit 0
fi

# Check for python3/python
if command -v python3 &> /dev/null; then
PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
PYTHON_CMD="python"
echo "⚠️  Using 'python' instead of 'python3'" >&2
else
echo "⚠️  No Python interpreter found, defaulting to ask" >&2
exit 0
fi

debug_log "Using Python command: $PYTHON_CMD"
debug_log "Calling AI analyzer..."

# Call AI analyzer
$PYTHON_CMD "$AI_ANALYZER" <<< "$INPUT"
AI_EXIT_CODE=$?

debug_log "AI analyzer exit code: $AI_EXIT_CODE"
exit $AI_EXIT_CODE
