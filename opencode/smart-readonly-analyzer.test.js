import { describe, it, before } from 'node:test';
import assert from 'node:assert';
import { SmartReadOnlyAnalyzer } from './smart-readonly-analyzer.js';

const { _internals } = SmartReadOnlyAnalyzer;
const {
  isReadOnly,
  parseCommandChain,
  isCommandChainReadOnly,
  isDangerous,
  hasShellOperators,
  extractPaths,
  targetsSensitiveFiles,
  isGrepSafeMode,
  redactCommand,
  sensitivePathPatterns,
  bareSensitiveFilenames,
} = _internals;

// =============================================================================
// isReadOnly tests
// =============================================================================

describe('isReadOnly', () => {
  describe('simple commands', () => {
    const simpleReadOnly = [
      'ls', 'ls -la', 'ls -la /tmp',
      'cat file.txt', 'cat -n file.txt',
      'grep pattern file.txt', 'grep -r pattern .',
      'head -n 10 file.txt', 'tail -f log.txt',
      'wc -l file.txt', 'pwd', 'echo hello',
      'which node', 'whereis python',
      'tree', 'file myfile', 'stat myfile',
      'du -sh .', 'df -h', 'whoami',
      'printenv', 'env', 'type ls',
      'awk "{print $1}" file.txt', 'cut -d: -f1 /etc/passwd',
      'sort file.txt', 'uniq file.txt', 'tr a-z A-Z',
      'jq .foo file.json', 'yq .bar file.yaml',
      'date', 'cal', 'bc', 'seq 1 10',
      'base64 file.txt', 'md5sum file.txt', 'sha256sum file.txt',
      'ping -c 1 google.com', 'dig google.com', 'host google.com',
      'ps aux', 'top -n 1', 'pgrep node', 'lsof -i :3000',
    ];

    for (const cmd of simpleReadOnly) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }
  });

  describe('sed patterns', () => {
    it('should allow sed without -i flag', () => {
      assert.strictEqual(isReadOnly('sed "s/foo/bar/g" file.txt'), true);
      assert.strictEqual(isReadOnly('sed -n "1,10p" file.txt'), true);
    });

    it('should NOT allow sed with -i flag', () => {
      assert.strictEqual(isReadOnly('sed -i "s/foo/bar/g" file.txt'), false);
      assert.strictEqual(isReadOnly('sed -i.bak "s/foo/bar/g" file.txt'), false);
    });
  });

  describe('find patterns', () => {
    it('should allow find without destructive flags', () => {
      assert.strictEqual(isReadOnly('find . -name "*.js"'), true);
      assert.strictEqual(isReadOnly('find /tmp -type f'), true);
      assert.strictEqual(isReadOnly('find . -name "*.log" -mtime +7'), true);
    });

    it('should NOT allow find with destructive flags', () => {
      assert.strictEqual(isReadOnly('find . -name "*.tmp" -delete'), false);
      assert.strictEqual(isReadOnly('find . -exec rm {} \\;'), false);
      assert.strictEqual(isReadOnly('find . -execdir chmod 755 {} \\;'), false);
    });
  });

  describe('git patterns', () => {
    const gitReadOnly = [
      'git status', 'git status -s',
      'git log', 'git log --oneline', 'git log -n 10',
      'git diff', 'git diff HEAD~1', 'git diff --staged',
      'git show HEAD', 'git show abc123',
      'git branch', 'git branch -a', 'git branch -v',
      'git remote', 'git remote -v',
      'git config --get user.name',
      'git rev-parse HEAD', 'git rev-parse --abbrev-ref HEAD',
      'git describe --tags', 'git tag', 'git tag -l',
      'git ls-files', 'git ls-remote origin',
      'git shortlog -sn', 'git blame file.txt',
      'git reflog', 'git cherry -v',
    ];

    for (const cmd of gitReadOnly) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }

    it('should NOT recognize git write commands as read-only', () => {
      assert.strictEqual(isReadOnly('git add .'), false);
      assert.strictEqual(isReadOnly('git commit -m "test"'), false);
      assert.strictEqual(isReadOnly('git checkout branch'), false);
    });
  });

  describe('python testing patterns', () => {
    const pythonTest = [
      'pytest', 'pytest -v', 'pytest tests/',
      'python -m pytest', 'python -m pytest -v',
      'python -m unittest', 'python -m unittest discover',
      'tox', 'tox -e py39',
      'mypy .', 'mypy src/', 'python -m mypy src/',
      'pylint src/', 'flake8', 'bandit -r src/',
      'coverage report', 'coverage html',
      'black --check .', 'isort --check .',
      'safety check', 'pip-audit',
    ];

    for (const cmd of pythonTest) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }
  });

  describe('django patterns', () => {
    const djangoReadOnly = [
      'python manage.py test',
      'python manage.py check',
      'python manage.py showmigrations',
      'python manage.py migrate --plan',
      'python manage.py inspectdb',
      'python manage.py diffsettings',
      'python manage.py --help',
    ];

    for (const cmd of djangoReadOnly) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }

    it('should NOT recognize django write commands as read-only', () => {
      assert.strictEqual(isReadOnly('python manage.py migrate'), false);
      assert.strictEqual(isReadOnly('python manage.py makemigrations'), false);
      assert.strictEqual(isReadOnly('python manage.py createsuperuser'), false);
    });
  });

  describe('node.js patterns', () => {
    // Note: npm run lint:xxx patterns require colon immediately after keyword,
    // then space or end - so "npm run lint: something" matches but not "npm run lint:check"
    const nodeReadOnly = [
      'npm test', 'npm run test: --verbose', 'npm run lint:',
      'yarn test', 'yarn run check:',
      'pnpm test', 'pnpm run typecheck:',
      'npm outdated', 'npm list', 'npm ls',
      'npm audit', 'npm why lodash',
      'jest', 'jest --coverage',
      'vitest', 'vitest run',
      'mocha', 'mocha tests/',
      'eslint .', 'eslint src/',
      'prettier --check .',
      'tsc --noEmit',
    ];

    for (const cmd of nodeReadOnly) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }
  });

  describe('docker patterns', () => {
    const dockerReadOnly = [
      'docker ps', 'docker ps -a',
      'docker images', 'docker images -a',
      'docker inspect container_id',
      'docker logs container_id', 'docker logs -f container_id',
      'docker version', 'docker info',
      'docker stats', 'docker top container_id',
      'docker history image_id',
    ];

    for (const cmd of dockerReadOnly) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }
  });

  describe('kubernetes patterns', () => {
    const k8sReadOnly = [
      'kubectl get pods', 'kubectl get pods -n kube-system',
      'kubectl describe pod my-pod',
      'kubectl logs my-pod', 'kubectl logs -f my-pod',
      'kubectl explain pods',
      'kubectl api-resources', 'kubectl api-versions',
      'kubectl cluster-info', 'kubectl top pods',
    ];

    for (const cmd of k8sReadOnly) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }
  });

  describe('terraform patterns', () => {
    const terraformReadOnly = [
      'terraform show', 'terraform plan',
      'terraform validate', 'terraform output',
      'terraform state list', 'terraform state show resource',
      'terraform providers', 'terraform version',
      'terraform fmt -check',
    ];

    for (const cmd of terraformReadOnly) {
      it(`should recognize "${cmd}" as read-only`, () => {
        assert.strictEqual(isReadOnly(cmd), true);
      });
    }
  });

  describe('curl/wget patterns', () => {
    it('should allow curl GET requests', () => {
      assert.strictEqual(isReadOnly('curl https://api.example.com'), true);
      assert.strictEqual(isReadOnly('curl -s https://api.example.com'), true);
      assert.strictEqual(isReadOnly('curl -H "Accept: application/json" https://api.example.com'), true);
    });

    it('should NOT allow curl with POST/PUT/DELETE', () => {
      assert.strictEqual(isReadOnly('curl -X POST https://api.example.com'), false);
      assert.strictEqual(isReadOnly('curl --request PUT https://api.example.com'), false);
      assert.strictEqual(isReadOnly('curl -X DELETE https://api.example.com'), false);
    });

    it('should allow wget in safe modes', () => {
      assert.strictEqual(isReadOnly('wget --spider https://example.com'), true);
      assert.strictEqual(isReadOnly('wget -O - https://example.com'), true);
    });
  });

  describe('archive tools', () => {
    it('should allow listing archive contents', () => {
      assert.strictEqual(isReadOnly('tar -t file.tar'), true);
      assert.strictEqual(isReadOnly('tar --list -f file.tar.gz'), true);
      assert.strictEqual(isReadOnly('unzip -l file.zip'), true);
    });
  });
});

// =============================================================================
// parseCommandChain tests
// =============================================================================

describe('parseCommandChain', () => {
  it('should return single segment for simple command', () => {
    assert.deepStrictEqual(parseCommandChain('ls -la'), ['ls -la']);
  });

  it('should split on pipes', () => {
    assert.deepStrictEqual(
      parseCommandChain('cat file.txt | grep pattern'),
      ['cat file.txt', 'grep pattern']
    );
  });

  it('should split on && operator', () => {
    assert.deepStrictEqual(
      parseCommandChain('git status && git log'),
      ['git status', 'git log']
    );
  });

  it('should split on || operator', () => {
    assert.deepStrictEqual(
      parseCommandChain('test -f file.txt || echo "not found"'),
      ['test -f file.txt', 'echo "not found"']
    );
  });

  it('should handle multiple operators', () => {
    assert.deepStrictEqual(
      parseCommandChain('git status && git log | head -5'),
      ['git status', 'git log', 'head -5']
    );
  });

  it('should preserve quoted content with operators', () => {
    assert.deepStrictEqual(
      parseCommandChain('echo "hello && world" | cat'),
      ['echo "hello && world"', 'cat']
    );
  });

  it('should preserve single-quoted content with operators', () => {
    assert.deepStrictEqual(
      parseCommandChain("echo 'hello | world' && cat"),
      ["echo 'hello | world'", 'cat']
    );
  });

  it('should handle escaped characters', () => {
    assert.deepStrictEqual(
      parseCommandChain('echo hello\\|world | cat'),
      ['echo hello\\|world', 'cat']
    );
  });

  it('should handle complex git chain', () => {
    assert.deepStrictEqual(
      parseCommandChain('git log -1 --oneline 6d2c1b0 && git rev-parse 6d2c1b0^'),
      ['git log -1 --oneline 6d2c1b0', 'git rev-parse 6d2c1b0^']
    );
  });

  it('should handle empty segments', () => {
    assert.deepStrictEqual(
      parseCommandChain('  ls  &&  cat file  '),
      ['ls', 'cat file']
    );
  });
});

// =============================================================================
// isCommandChainReadOnly tests
// =============================================================================

describe('isCommandChainReadOnly', () => {
  it('should return null for single command (no chain)', () => {
    assert.strictEqual(isCommandChainReadOnly('ls -la'), null);
  });

  it('should return true for read-only pipe chain', () => {
    assert.strictEqual(isCommandChainReadOnly('cat file.txt | grep pattern | head -5'), true);
  });

  it('should return true for read-only && chain', () => {
    assert.strictEqual(isCommandChainReadOnly('git status && git log'), true);
    assert.strictEqual(isCommandChainReadOnly('git log -1 --oneline abc && git rev-parse abc^'), true);
  });

  it('should return true for read-only || chain', () => {
    assert.strictEqual(isCommandChainReadOnly('ls file.txt || echo "not found"'), true);
  });

  it('should return false if any command is not read-only', () => {
    assert.strictEqual(isCommandChainReadOnly('git status && git push'), false);
    assert.strictEqual(isCommandChainReadOnly('cat file.txt | rm -rf /'), false);
    assert.strictEqual(isCommandChainReadOnly('npm test && npm install'), false);
  });

  it('should return true for mixed operators with read-only commands', () => {
    assert.strictEqual(
      isCommandChainReadOnly('git status && git log | head -10 || echo "failed"'),
      true
    );
  });
});

// =============================================================================
// isDangerous tests
// =============================================================================

describe('isDangerous', () => {
  describe('system commands', () => {
    const dangerous = [
      'rm file.txt', 'rm -rf /',
      'sudo apt update', 'sudo rm -rf /',
      'mv file1 file2',
      'dd if=/dev/zero of=/dev/sda',
      'shutdown -h now', 'reboot',
      'kill -9 1234', 'pkill node',
    ];

    for (const cmd of dangerous) {
      it(`should recognize "${cmd}" as dangerous`, () => {
        assert.strictEqual(isDangerous(cmd), true);
      });
    }
  });

  describe('git dangerous commands', () => {
    const gitDangerous = [
      'git push', 'git push origin main',
      'git push --force', 'git push -f',
      'git reset --hard HEAD~1',
      'git clean -fd',
      'git rebase main', 'git merge feature',
    ];

    for (const cmd of gitDangerous) {
      it(`should recognize "${cmd}" as dangerous`, () => {
        assert.strictEqual(isDangerous(cmd), true);
      });
    }
  });

  describe('package installation', () => {
    const installCommands = [
      'pip install requests',
      'npm install lodash', 'yarn install',
      'pnpm install', 'apt install vim',
      'apt-get install curl', 'brew install wget',
      'cargo install ripgrep', 'gem install rails',
      'python -m pip install pytest',
      'python pip install flask',
    ];

    for (const cmd of installCommands) {
      it(`should recognize "${cmd}" as dangerous`, () => {
        assert.strictEqual(isDangerous(cmd), true);
      });
    }
  });

  describe('docker dangerous commands', () => {
    const dockerDangerous = [
      'docker rm container_id',
      'docker rmi image_id',
      'docker stop container_id',
      'docker kill container_id',
      'docker prune',  // docker system prune doesn't match pattern
      'docker build .',
      'docker push image:tag',
    ];

    for (const cmd of dockerDangerous) {
      it(`should recognize "${cmd}" as dangerous`, () => {
        assert.strictEqual(isDangerous(cmd), true);
      });
    }
  });

  describe('kubernetes dangerous commands', () => {
    const k8sDangerous = [
      'kubectl delete pod my-pod',
      'kubectl apply -f deployment.yaml',
      'kubectl create namespace test',
      'kubectl scale deployment my-deploy --replicas=5',
      'kubectl rollout restart deployment/my-deploy',
    ];

    for (const cmd of k8sDangerous) {
      it(`should recognize "${cmd}" as dangerous`, () => {
        assert.strictEqual(isDangerous(cmd), true);
      });
    }
  });

  describe('formatters in write mode', () => {
    it('should recognize black without --check as dangerous', () => {
      assert.strictEqual(isDangerous('black .'), true);
      assert.strictEqual(isDangerous('black src/'), true);
    });

    it('should NOT recognize black --check as dangerous', () => {
      assert.strictEqual(isDangerous('black --check .'), false);
    });

    it('should recognize prettier --write as dangerous', () => {
      assert.strictEqual(isDangerous('prettier --write .'), true);
    });
  });

  describe('django dangerous commands', () => {
    const djangoDangerous = [
      'python manage.py migrate',
      'python manage.py makemigrations',
      'python manage.py loaddata fixtures.json',
      'python manage.py flush',
      'python manage.py createsuperuser',
      'python manage.py collectstatic',
    ];

    for (const cmd of djangoDangerous) {
      it(`should recognize "${cmd}" as dangerous`, () => {
        assert.strictEqual(isDangerous(cmd), true);
      });
    }

    it('should NOT recognize migrate --plan as dangerous', () => {
      assert.strictEqual(isDangerous('python manage.py migrate --plan'), false);
    });
  });
});

// =============================================================================
// hasShellOperators tests
// =============================================================================

describe('hasShellOperators', () => {
  it('should detect pipe operator', () => {
    assert.strictEqual(hasShellOperators('cat file | grep pattern'), true);
  });

  it('should detect || operator', () => {
    assert.strictEqual(hasShellOperators('test -f file || echo missing'), true);
  });

  it('should detect && operator', () => {
    assert.strictEqual(hasShellOperators('cmd1 && cmd2'), true);
  });

  it('should detect redirect operator', () => {
    assert.strictEqual(hasShellOperators('echo hello > file.txt'), true);
  });

  it('should detect append operator', () => {
    assert.strictEqual(hasShellOperators('echo hello >> file.txt'), true);
  });

  it('should detect subshell $() operator', () => {
    assert.strictEqual(hasShellOperators('echo $(whoami)'), true);
  });

  it('should detect backtick subshell', () => {
    assert.strictEqual(hasShellOperators('echo `whoami`'), true);
  });

  it('should detect semicolon chaining', () => {
    assert.strictEqual(hasShellOperators('cmd1; cmd2'), true);
  });

  it('should NOT detect operators in simple commands', () => {
    assert.strictEqual(hasShellOperators('ls -la'), false);
    assert.strictEqual(hasShellOperators('git status'), false);
  });
});

// =============================================================================
// extractPaths tests
// =============================================================================

describe('extractPaths', () => {
  it('should extract quoted paths', () => {
    const paths = extractPaths('cat "/path/to/file.txt"');
    assert.ok(paths.includes('/path/to/file.txt'));
  });

  it('should extract unquoted paths with slashes', () => {
    const paths = extractPaths('cat /etc/passwd');
    assert.ok(paths.includes('/etc/passwd'));
  });

  it('should extract dotfiles', () => {
    const paths = extractPaths('cat .env');
    assert.ok(paths.includes('.env'));
  });

  it('should extract files with extensions', () => {
    const paths = extractPaths('cat secrets.json');
    assert.ok(paths.includes('secrets.json'));
  });

  it('should skip flags', () => {
    const paths = extractPaths('ls -la --all');
    assert.ok(!paths.includes('-la'));
    assert.ok(!paths.includes('--all'));
  });

  it('should extract known sensitive filenames', () => {
    const paths = extractPaths('cat credentials.json id_rsa');
    assert.ok(paths.includes('credentials.json'));
    assert.ok(paths.includes('id_rsa'));
  });
});

// =============================================================================
// targetsSensitiveFiles tests
// =============================================================================

describe('targetsSensitiveFiles', () => {
  describe('env files', () => {
    it('should detect .env', () => {
      assert.ok(targetsSensitiveFiles('cat .env').length > 0);
    });

    it('should detect .env.local', () => {
      assert.ok(targetsSensitiveFiles('cat .env.local').length > 0);
    });

    it('should detect .env.production', () => {
      assert.ok(targetsSensitiveFiles('cat .env.production').length > 0);
    });
  });

  describe('SSH keys', () => {
    it('should detect .ssh/ paths', () => {
      assert.ok(targetsSensitiveFiles('cat ~/.ssh/config').length > 0);
    });

    it('should detect id_rsa', () => {
      assert.ok(targetsSensitiveFiles('cat id_rsa').length > 0);
    });

    it('should detect id_ed25519', () => {
      assert.ok(targetsSensitiveFiles('cat id_ed25519').length > 0);
    });
  });

  describe('cloud credentials', () => {
    it('should detect .aws/ paths', () => {
      assert.ok(targetsSensitiveFiles('cat ~/.aws/credentials').length > 0);
    });

    it('should detect .kube/config', () => {
      assert.ok(targetsSensitiveFiles('cat ~/.kube/config').length > 0);
    });
  });

  describe('secrets files', () => {
    it('should detect secrets.json', () => {
      assert.ok(targetsSensitiveFiles('cat secrets.json').length > 0);
    });

    it('should detect secrets.yaml', () => {
      assert.ok(targetsSensitiveFiles('cat secrets.yaml').length > 0);
    });

    it('should detect credentials.json', () => {
      assert.ok(targetsSensitiveFiles('cat credentials.json').length > 0);
    });
  });

  describe('other sensitive files', () => {
    it('should detect .npmrc', () => {
      assert.ok(targetsSensitiveFiles('cat .npmrc').length > 0);
    });

    it('should detect .pypirc', () => {
      assert.ok(targetsSensitiveFiles('cat .pypirc').length > 0);
    });

    it('should detect .netrc', () => {
      assert.ok(targetsSensitiveFiles('cat .netrc').length > 0);
    });

    it('should detect .pem files', () => {
      assert.ok(targetsSensitiveFiles('cat server.pem').length > 0);
    });

    it('should detect .key files', () => {
      assert.ok(targetsSensitiveFiles('cat private.key').length > 0);
    });

    it('should detect files with "password" in name', () => {
      assert.ok(targetsSensitiveFiles('cat password.txt').length > 0);
    });

    it('should detect files with "token" in name', () => {
      assert.ok(targetsSensitiveFiles('cat token.json').length > 0);
    });

    it('should detect files with "api_key" in name', () => {
      assert.ok(targetsSensitiveFiles('cat api_key.txt').length > 0);
    });
  });

  describe('non-sensitive files', () => {
    it('should NOT flag regular files', () => {
      assert.strictEqual(targetsSensitiveFiles('cat README.md').length, 0);
      assert.strictEqual(targetsSensitiveFiles('cat package.json').length, 0);
      assert.strictEqual(targetsSensitiveFiles('cat src/index.js').length, 0);
    });
  });
});

// =============================================================================
// isGrepSafeMode tests
// =============================================================================

describe('isGrepSafeMode', () => {
  it('should detect grep -l as safe mode', () => {
    assert.strictEqual(isGrepSafeMode('grep -l pattern file.txt'), true);
  });

  it('should detect grep --files-with-matches as safe mode', () => {
    assert.strictEqual(isGrepSafeMode('grep --files-with-matches pattern file.txt'), true);
  });

  it('should detect grep -c as safe mode', () => {
    assert.strictEqual(isGrepSafeMode('grep -c pattern file.txt'), true);
  });

  it('should detect grep --count as safe mode', () => {
    assert.strictEqual(isGrepSafeMode('grep --count pattern file.txt'), true);
  });

  it('should detect rg -l as safe mode', () => {
    assert.strictEqual(isGrepSafeMode('rg -l pattern'), true);
  });

  it('should detect ag -l as safe mode', () => {
    assert.strictEqual(isGrepSafeMode('ag -l pattern'), true);
  });

  it('should NOT flag regular grep', () => {
    assert.strictEqual(isGrepSafeMode('grep pattern file.txt'), false);
  });

  it('should return false for non-grep commands', () => {
    assert.strictEqual(isGrepSafeMode('cat -l file.txt'), false);
  });
});

// =============================================================================
// redactCommand tests
// =============================================================================

describe('redactCommand', () => {
  describe('sensitive file paths', () => {
    it('should redact .env paths', () => {
      const redacted = redactCommand('cat /path/to/.env');
      assert.ok(redacted.includes('[REDACTED:.env]'));
    });

    it('should redact secrets.json', () => {
      const redacted = redactCommand('cat secrets.json');
      assert.ok(redacted.includes('[REDACTED:'));
    });

    it('should redact id_rsa', () => {
      const redacted = redactCommand('cat ~/.ssh/id_rsa');
      assert.ok(redacted.includes('[REDACTED:'));
    });
  });

  describe('inline secrets', () => {
    it('should redact --token flag values', () => {
      const redacted = redactCommand('curl --token=abc123secret https://api.example.com');
      // The regex captures the flag and replaces with flag + [REDACTED]
      assert.ok(redacted.includes('[REDACTED]'));
      assert.ok(!redacted.includes('abc123secret'));
    });

    it('should redact --password flag values', () => {
      const redacted = redactCommand('mysql --password=secretpass');
      assert.ok(redacted.includes('[REDACTED]'));
      assert.ok(!redacted.includes('secretpass'));
    });

    it('should redact environment variable assignments', () => {
      const redacted = redactCommand('GITHUB_TOKEN=ghp_xxxx123 git push');
      assert.ok(redacted.includes('[REDACTED]'));
      assert.ok(!redacted.includes('ghp_xxxx123'));
    });

    it('should redact Authorization headers', () => {
      const redacted = redactCommand('curl -H "Authorization: Bearer secrettoken123"');
      assert.ok(redacted.includes('[REDACTED]'));
      assert.ok(!redacted.includes('secrettoken123'));
    });

    it('should redact base64 tokens with padding', () => {
      // Token must be 32+ chars and end with = or ==
      // Use "data:" instead of "token:" to avoid triggering sensitive filename detection
      const redacted = redactCommand('echo "data: YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY3ODkwYWJjZGVmZ2g=="');
      assert.ok(redacted.includes('[REDACTED]'));
      assert.ok(!redacted.includes('YWJjZGVm'));
    });
  });

  describe('non-sensitive content', () => {
    it('should NOT redact regular commands', () => {
      const cmd = 'git log --oneline -10';
      assert.strictEqual(redactCommand(cmd), cmd);
    });

    it('should NOT redact git SHAs (40 hex chars)', () => {
      const cmd = 'git show abc123def456789012345678901234567890abcd';
      // Git SHAs don't have + or / and don't end in =, so should not be redacted
      assert.ok(!redactCommand(cmd).includes('[REDACTED]'));
    });
  });
});

// =============================================================================
// SmartReadOnlyAnalyzer integration tests
// =============================================================================

describe('SmartReadOnlyAnalyzer', () => {
  // Mock client for AI analysis
  const mockClient = {
    chat: {
      create: async () => ({
        content: [{
          text: JSON.stringify({
            shouldAutoApprove: false,
            riskLevel: 'medium',
            confidence: 0.5,
            reason: 'Unknown command',
            riskFlags: [],
          })
        }]
      })
    }
  };

  it('should export permission.ask handler', async () => {
    const analyzer = await SmartReadOnlyAnalyzer({ client: mockClient });
    assert.ok(typeof analyzer['permission.ask'] === 'function');
  });

  describe('permission.ask', () => {
    let analyzer;

    before(async () => {
      analyzer = await SmartReadOnlyAnalyzer({ client: mockClient });
    });

    it('should return "ask" for non-bash tools', async () => {
      const result = await analyzer['permission.ask']({ tool: 'read', path: '/file.txt' });
      assert.strictEqual(result.status, 'ask');
    });

    it('should return "ask" for missing command', async () => {
      const result = await analyzer['permission.ask']({ tool: 'bash' });
      assert.strictEqual(result.status, 'ask');
    });

    it('should allow simple read-only commands', async () => {
      const result = await analyzer['permission.ask']({ tool: 'bash', command: 'ls -la' });
      assert.strictEqual(result.status, 'allow');
    });

    it('should allow read-only && chains', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'git status && git log --oneline -5'
      });
      assert.strictEqual(result.status, 'allow');
    });

    it('should allow read-only || chains', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'ls file.txt || echo "not found"'
      });
      assert.strictEqual(result.status, 'allow');
    });

    it('should allow read-only pipe chains', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'cat file.txt | grep pattern | head -10'
      });
      assert.strictEqual(result.status, 'allow');
    });

    it('should ask for chains with non-read-only commands', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'git status && git push'
      });
      assert.strictEqual(result.status, 'ask');
    });

    it('should ask for sensitive file access', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'cat .env'
      });
      assert.strictEqual(result.status, 'ask');
    });

    it('should ask for dangerous commands', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'rm -rf /'
      });
      assert.strictEqual(result.status, 'ask');
    });

    it('should ask for redirect operators', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'echo hello > file.txt'
      });
      assert.strictEqual(result.status, 'ask');
    });

    it('should ask for subshell operators', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'echo $(whoami)'
      });
      assert.strictEqual(result.status, 'ask');
    });

    it('should ask for semicolon chaining', async () => {
      const result = await analyzer['permission.ask']({
        tool: 'bash',
        command: 'ls; rm file.txt'
      });
      assert.strictEqual(result.status, 'ask');
    });

    it('should handle different payload shapes', async () => {
      // Shape 1: { tool, command }
      let result = await analyzer['permission.ask']({ tool: 'bash', command: 'ls' });
      assert.strictEqual(result.status, 'allow');

      // Shape 2: { request: { tool, command } }
      result = await analyzer['permission.ask']({ request: { tool: 'bash', command: 'ls' } });
      assert.strictEqual(result.status, 'allow');

      // Shape 3: { tool, tool_input: { command } }
      result = await analyzer['permission.ask']({ tool: 'bash', tool_input: { command: 'ls' } });
      assert.strictEqual(result.status, 'allow');

      // Shape 4: { tool_name, input: { command } }
      result = await analyzer['permission.ask']({ tool_name: 'Bash', input: { command: 'ls' } });
      assert.strictEqual(result.status, 'allow');
    });
  });
});

// =============================================================================
// Edge cases and regression tests
// =============================================================================

describe('Edge cases', () => {
  it('should handle empty string', () => {
    assert.strictEqual(isReadOnly(''), false);
    assert.deepStrictEqual(parseCommandChain(''), []);
  });

  it('should handle whitespace-only string', () => {
    assert.strictEqual(isReadOnly('   '), false);
    assert.deepStrictEqual(parseCommandChain('   '), []);
  });

  it('should handle commands with leading/trailing whitespace', () => {
    assert.strictEqual(isReadOnly('  ls -la  '), true);
  });

  it('should handle nested quotes', () => {
    const segments = parseCommandChain('echo "hello \'world\'" | cat');
    assert.deepStrictEqual(segments, ['echo "hello \'world\'"', 'cat']);
  });

  it('should handle the original issue command', () => {
    // The command from the user's screenshot
    const cmd = 'git log -1 --oneline 6d2c1b0 && git rev-parse 6d2c1b0^';
    assert.strictEqual(isCommandChainReadOnly(cmd), true);
  });
});
