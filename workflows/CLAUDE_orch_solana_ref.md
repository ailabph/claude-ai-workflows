# Claude Orchestrator Solana - Quick Reference

Supplementary reference for `CLAUDE_orch_solana.md`.

---

## Two-Agent Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SOLANA TWO-SESSION ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SESSION 1: REVIEWER (Opus)             SESSION 2: EXECUTOR (Sonnet)         │
│  ──────────────────────────             ────────────────────────────         │
│                                                                              │
│  ┌─────────────────────┐                                                     │
│  │ 1. Create Plan      │                                                     │
│  │    DOC_program.md   │                                                     │
│  └──────────┬──────────┘                                                     │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐    copy prompt    ┌─────────────────────┐          │
│  │ 2. Generate         │ ─────────────────▶│ 3. Execute          │          │
│  │    Executor Prompt  │                   │    Milestone 1      │          │
│  └─────────────────────┘                   └──────────┬──────────┘          │
│                                                       │                      │
│                                                       ▼                      │
│  ┌─────────────────────┐    copy report    ┌─────────────────────┐          │
│  │ 4. Review Report    │ ◀─────────────────│ 4. STOP + Report    │          │
│  │    + Security Check │                   │    [PROGRESS_REPORT]│          │
│  └──────────┬──────────┘                   └─────────────────────┘          │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐                                                     │
│  │ 5. Approve/Reject   │──── if approved ────┐                              │
│  │    [MILESTONE_      │                     │                              │
│  │     APPROVED]       │                     ▼                              │
│  └─────────────────────┘      ┌─────────────────────┐                       │
│             │                 │ 6. Continue         │                       │
│             │   copy prompt   │    Milestone N+1    │                       │
│             └────────────────▶│                     │                       │
│                               └─────────────────────┘                       │
│                                                                              │
│  [Repeat until devnet deployment complete]                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Kickstart Prompts (Copy-Paste)

### Start Reviewer Session
```
Read CLAUDE_orch_solana.md. You are the REVIEWER agent.

Create an implementation plan for: [SOLANA PROGRAM DESCRIPTION]

1. Research the codebase to understand existing Anchor patterns
2. Create plan at: docs/[feature]/DOC_[feature]_plan.md
3. Define 3-5 milestones with security requirements
4. Generate the executor prompt for Milestone 1

After creating the plan, show me the prompt to send to the executor agent.
```

### Start Executor Session
```
Read CLAUDE_orch_solana.md. You are the EXECUTOR agent.

[PASTE PROMPT FROM REVIEWER AGENT]
```

### Reviewer: Approve & Continue
```
Milestone [N] approved.

Generate the prompt for the executor to continue with Milestone [N+1].
```

### Reviewer: Request Changes
```
Milestone [N] needs changes:
- [Issue 1]
- [Issue 2]

Generate a prompt for the executor to fix these issues.
```

### Reviewer: Security Concerns
```
Milestone [N] has security issues:
- [Vulnerability 1]
- [Vulnerability 2]

Generate a prompt for the executor to address these security concerns.
```

### Executor: Continue
```
Milestone [N] approved. Continue with Milestone [N+1]:

[PASTE NEXT MILESTONE DETAILS FROM REVIEWER]
```

---

## Recovery Prompts (Copy-Paste)

### Recover Reviewer Session
```
Read CLAUDE_orch_solana.md. You are the REVIEWER agent.

Recovering session for: [PROGRAM NAME]

Plan document: docs/[feature]/DOC_[feature]_plan.md

Current status:
- Milestones approved: [1, 2, ...]
- Current milestone: [N] (executor working / awaiting review)
- Security issues: [None / description]
- Blocking issues: [None / description]

[If executor submitted report, paste it here]

Continue reviewing from where we left off.
```

### Recover Executor Session (Same Session)
```
Context was compressed. Re-read:
- CLAUDE_orch_solana.md
- The plan document

Continue Milestone [N] from where we left off.
Last completed: [file/instruction]
Run `anchor build` and `anchor test` before reporting.
```

### Recover Executor Session (New Session)
```
Read CLAUDE_orch_solana.md. You are the EXECUTOR agent.

Milestone [N] is IN PROGRESS. Previous executor crashed.

Plan document: [path]

Completed so far:
- [file1] created
- [instruction1] implemented

Remaining:
- [instruction2]
- [tests]

Continue from where the previous executor left off.
Stop and report when milestone is complete.
```

---

## Session State Template

Reviewer should track progress:

```markdown
## Session State: [Program Name]

**Plan**: docs/[feature]/DOC_[feature]_plan.md
**Network**: localnet → devnet

| Milestone | Status | Commit | Security |
|-----------|--------|--------|----------|
| M1: Setup + State | ✅ Approved | `abc123` | ✓ PDAs valid |
| M2: Instructions | ✅ Approved | `def456` | ✓ Signers checked |
| M3: Tests | 🔄 In Progress | - | - |
| M4: Devnet | ⏳ Pending | - | - |

**Current**: Executor working on M3
**Blocking**: None
**Program ID**: TBD (after M4)
**Last Update**: [timestamp]
```

---

## Response Format Tags (orchestrator-auto)

### Planner Tags
| Tag | Usage |
|-----|-------|
| `[PLAN_READY]` | Plan created, include path and milestone count |
| `[PLAN_CONTENT]...[/PLAN_CONTENT]` | Wraps plan content |
| `[MILESTONE_APPROVED]` | Milestone passes review |
| `[CHANGES_REQUESTED]` | Needs fixes before approval |
| `[HUMAN_INPUT_NEEDED]` | Blocker needing human input |

### Executor Tags
| Tag | Usage |
|-----|-------|
| `[PROGRESS_REPORT]...[/PROGRESS_REPORT]` | Milestone completion |
| `[CLARIFICATION_NEEDED]` | Need planner clarification |
| `[BLOCKED]` | External blocker |

---

## Progress Report Template

```markdown
[PROGRESS_REPORT]
## Milestone [N]: [Name] - COMPLETED

### Files Created/Modified:
- programs/[name]/src/lib.rs (modified)
- programs/[name]/src/instructions/stake.rs (created)
- programs/[name]/src/state/vault.rs (created)
- tests/[name].ts (modified)

### Build Output:
```
anchor build
# Build successful
```

### Test Results:
```
anchor test
# [paste output]
```

### Security Checklist:
- [x] Signer verification
- [x] PDA validation
- [x] Checked arithmetic
- [x] Owner checks
- [ ] CPI security (N/A)

### Git Checkpoint:
`abc1234` - feat(solana/staking): complete M[N] - [description]

### Notes/Issues:
[Any blockers, deviations, or questions]

### Ready for Review: YES
[/PROGRESS_REPORT]
```

### Final Milestone Addition
```markdown
### Devnet Deployment:
- Program ID: `[PublicKey]`
- IDL Published: Yes
- Explorer: https://explorer.solana.com/address/[PubKey]?cluster=devnet

### Coverage Report:
[paste coverage if available]

### TASK COMPLETE - Ready for Final Review
```

---

## Review Commands

| Action | Command |
|--------|---------|
| **Approve** | `Milestone [N] approved. Generate prompt for M[N+1].` |
| **Changes needed** | `Milestone [N] needs changes: [issues]. Generate fix prompt.` |
| **Security issue** | `Milestone [N] has security issues: [vulnerabilities]. Generate fix prompt.` |
| **Approve with notes** | `Milestone [N] approved with notes: [observations]. Generate prompt for M[N+1].` |
| **Abort** | `ABORT: [Reason]. Do not proceed.` |

---

## Milestone Patterns by Program Type

| Program Type | M1 | M2 | M3 | M4 | M5 |
|--------------|----|----|----|----|-----|
| **Anchor Program** | Setup + State | Instructions | Tests | Devnet | Docs/SDK |
| **Token Program** | SPL Setup | Mint/Transfer | Metadata | Tests | Deploy |
| **NFT Collection** | Metaplex Setup | Minting | Collection | Tests | Deploy |
| **DeFi Protocol** | AMM Design | Core Math | Swap/LP | Audit | Deploy |
| **Staking** | Vault State | Stake/Unstake | Rewards | Tests | Deploy |
| **Governance** | Proposal State | Voting Logic | Execution | Tests | Deploy |

---

## Security Checklist Quick Reference

### Every Instruction
```
[ ] Signer<'info> for privileged operations
[ ] has_one = authority constraint
[ ] PDA seeds validated
[ ] bump stored and checked
[ ] checked_add/checked_mul for math
[ ] Account ownership verified
```

### Pre-Devnet
```
[ ] All access control reviewed
[ ] No hardcoded keys
[ ] Error messages safe
[ ] Upgrade authority configured
[ ] IDL accurate
```

### Pre-Mainnet
```
[ ] Professional audit complete
[ ] Audit findings addressed
[ ] Multisig upgrade authority
[ ] Emergency pause (if needed)
[ ] Monitoring configured
```

---

## Common Vulnerabilities Reference

| Vulnerability | Check For | Mitigation |
|---------------|-----------|------------|
| Missing signer | No `Signer<'info>` type | Add signer constraint |
| Missing owner | Raw `AccountInfo` usage | Use `Account<'info, T>` |
| PDA substitution | Seeds not verified | Validate full derivation |
| Integer overflow | `+`, `-`, `*` operators | Use `checked_*` methods |
| Reentrancy | CPI before state update | Update state first |
| Rent drain | Manual close logic | Use `close = dest` |
| Type cosplay | Missing discriminator | Anchor handles, or manual |
| Arbitrary CPI | Unchecked program ID | Verify `program_id` |

---

## Anchor Commands Quick Reference

```bash
# Project Setup
anchor init [name]              # New project
anchor build                    # Build program
anchor test                     # Run tests
anchor test --skip-local-validator  # If validator already running

# Deployment
anchor deploy --provider.cluster localnet
anchor deploy --provider.cluster devnet
anchor deploy --provider.cluster mainnet

# IDL Management
anchor idl init --filepath target/idl/[name].json [PROGRAM_ID]
anchor idl upgrade --filepath target/idl/[name].json [PROGRAM_ID]
anchor idl fetch [PROGRAM_ID] --provider.cluster [cluster]

# Upgrade
anchor upgrade target/deploy/[name].so --program-id [PROGRAM_ID]
```

---

## Solana CLI Quick Reference

```bash
# Cluster
solana config set --url localhost    # localnet
solana config set --url devnet       # devnet
solana config set --url mainnet-beta # mainnet

# Local Validator
solana-test-validator               # Start
solana-test-validator --reset       # Fresh start

# Accounts
solana balance                      # Check balance
solana airdrop 2                    # Get SOL (devnet)
solana account [PUBKEY]             # View account

# Programs
solana program show [PROGRAM_ID]    # Program info
solana program dump [PROGRAM_ID] program.so  # Download
```

---

## Git Checkpoint Quick Reference

### Commit After Milestone Approval
```bash
git add -A
git commit -m "feat(solana/[program]): complete M[N] - [description]"
```

### Commit Message Formats
| Event | Format |
|-------|--------|
| Milestone complete | `feat(solana/[program]): complete M[N] - [description]` |
| Work in progress | `wip(solana/[program]): M[N] in progress - [status]` |
| Checkpoint | `chore(solana/[program]): checkpoint before [action]` |
| Security fix | `fix(solana/[program]): [vulnerability] - [fix description]` |

### Rollback Commands
```bash
git log --oneline -10                    # View recent
git reset --hard [commit-hash]           # Discard changes
git reset --soft [commit-hash]           # Keep changes unstaged
```

---

## Context Retention Quick Reference

### Critical Info by Agent

| Agent | Must Remember |
|-------|---------------|
| **Reviewer** | Plan path, milestone #, approved milestones, security issues |
| **Executor** | Plan path, milestone #, deliverables, test requirements, network |

### Re-read Triggers

**Reviewer** - Re-read if you:
- Forgot which milestones are approved
- Lost track of security checklist status
- Can't remember executor prompt format

**Executor** - Re-read if you:
- Forgot progress report format
- Don't remember to STOP after milestone
- Lost track of which network to target

### Compression Recovery
```
"Context was compressed. Let me re-read the workflow and plan to continue properly."
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent continues without stopping | Add **STOP** in bold, emphasize in prompt |
| Missing security checks | Include checklist in milestone requirements |
| Tests not running | Specify `anchor test` in deliverables |
| Wrong network | Explicitly state localnet/devnet in prompt |
| Build fails | Check Anchor version, dependencies |
| Deploy fails | Check SOL balance, program authority |
| Executor confused | Start fresh session with clearer prompt |
| Context compressed | Use recovery prompts |

---

## File Structure Reference

### Anchor Project
```
[project]/
├── Anchor.toml
├── Cargo.toml
├── programs/
│   └── [program-name]/
│       ├── Cargo.toml
│       └── src/
│           ├── lib.rs
│           ├── state/
│           │   ├── mod.rs
│           │   └── [accounts].rs
│           ├── instructions/
│           │   ├── mod.rs
│           │   ├── initialize.rs
│           │   └── [other].rs
│           ├── errors.rs
│           └── events.rs
├── tests/
│   └── [program-name].ts
├── migrations/
│   └── deploy.ts
└── target/
    ├── deploy/
    │   └── [program-name].so
    └── idl/
        └── [program-name].json
```

---

## Related Files

| File | Purpose |
|------|---------|
| `CLAUDE_orch_solana.md` | Full Solana framework + templates |
| `CLAUDE_orchestrator.md` | Base framework (backend/frontend) |
| `CLAUDE_orchestrator_ref.md` | Base quick reference |
| `docs/[feature]/DOC_[feature]_plan.md` | Implementation plans |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12 | Initial Solana reference based on CLAUDE_orchestrator_ref.md |
