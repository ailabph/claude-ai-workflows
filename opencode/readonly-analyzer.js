export const SmartReadOnlyAnalyzer = async ({ client }) => {
  // Known safe commands - instant approval
  const knownSafe = new Set([
    'ls', 'cat', 'grep', 'find', 'head', 'tail', 'pwd', 'echo',
    'git status', 'git log', 'git diff', 'wc', 'file'
  ]);

  // Known dangerous patterns - instant deny
  const dangerousPatterns = [
    /^rm\s/, /^mv\s/, /^cp\s.*>/, /^git\s+push/,
    /^sudo/, />\s*\//, /^curl.*-X\s+(POST|PUT|DELETE)/
  ];

  return {
    "permission.ask": async ({ request }) => {
      if (request.tool !== "bash") return { status: "ask" };

      const cmd = request.command.trim();
      const firstWord = cmd.split(/\s+/)[0];

      // Fast path: known safe
      if (knownSafe.has(firstWord) || knownSafe.has(cmd)) {
        return { status: "allow" };
      }

      // Fast path: known dangerous
      if (dangerousPatterns.some(p => p.test(cmd))) {
        return { status: "deny" };
      }

      // Use AI for uncertain cases
      const analysis = await analyzeCommandWithAI(client, cmd);

      if (analysis.isReadOnly && analysis.confidence > 0.85) {
        return { status: "allow" };
      }

      return { status: "ask" };
    }
  };
};
