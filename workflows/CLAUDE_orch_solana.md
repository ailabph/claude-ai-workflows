# Claude Orchestrator: Solana/Web3 Development Framework (v1.0)

## Overview

A **gated milestone workflow** for AI agents executing Solana smart contract development and Web3 integration tasks. Ensures human oversight at critical checkpoints for security review, validation, and course correction.

**Architecture**: Two separate Claude sessions - one as Reviewer/Planner, one as Executor - communicating through structured prompts with human as intermediary.

**Compatibility**: Fully compatible with `orchestrator-auto` CLI tool. Uses the same response format tags and workflow phases.

---

## IMPORTANT: Context Retention Instructions

> **FOR BOTH AGENTS**: This section contains critical instructions for maintaining workflow knowledge.

### On Context Compression (`/compact`)

**Reviewer Agent** - When context is compacted:
1. Re-read this file: `CLAUDE_orch_solana.md`
2. Re-read the plan document: `docs/[feature]/DOC_[feature]_plan.md`
3. Check milestone progress: Which milestones are approved?

**Executor Agent** - When context is compacted:
1. Re-read this file: `CLAUDE_orch_solana.md`
2. Re-read the plan document provided in your prompt
3. Check: What milestone am I on? What's left to do?

### Critical Information to Retain

| Agent | Must Remember |
|-------|---------------|
| **Reviewer** | Plan doc path, current milestone #, approved milestones, blocking issues, security checklist status |
| **Executor** | Plan doc path, current milestone #, deliverables checklist, test requirements, network (localnet/devnet/mainnet) |

### Compression Recovery Command

If context was compressed, tell the user:
```
"Context was compressed. Let me re-read the workflow and plan to continue properly."
```

Then read: `CLAUDE_orch_solana.md` and the relevant plan document.

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Milestone-Based** | Tasks divided into 3-5 discrete milestones with clear deliverables |
| **Gated Approval** | No milestone proceeds without explicit human approval |
| **Security-First** | Solana-specific security checklist at each milestone |
| **Structured Reports** | Standardized format: files changed, test results, security checks, issues |

---

## Quick Start

### Step 1: Create Implementation Plan
```
docs/{feature}/DOC_{feature_name}_plan.md
```
Include: program spec, account structures, instruction handlers, PDAs, testing requirements, security considerations.

### Step 2: Define Milestones (3-5)

| Project Type | Milestone Pattern |
|--------------|-------------------|
| **Anchor Program** | Project Setup → Account Structs + State → Instructions → Tests → Devnet Deploy |
| **Native Program** | Entrypoint + State → Instruction Processing → CPI Integration → Tests → Deploy |
| **Token Program** | SPL Setup → Mint/Transfer Logic → Metadata → Tests → Mainnet |
| **NFT Collection** | Metaplex Setup → Minting Logic → Collection Config → Tests → Deploy |
| **DeFi Protocol** | AMM/Vault Design → Core Math → Swap/LP Logic → Security Audit → Deploy |
| **Client SDK** | Types + Connection → Transaction Builders → Signing + Submit → Tests → Publish |

### Step 3: Execute + Review Loop
1. Give prompt to Claude → 2. Agent executes milestone, stops, reports → 3. Review and approve/reject → 4. Repeat

---

## Two-Agent Workflow

This framework is designed for a **two-agent architecture** to optimize context usage and model costs.

### Architecture

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│  PLANNER/REVIEWER                   │     │  EXECUTOR                           │
│  (Opus - expensive, strategic)      │     │  (Sonnet/Haiku - cost-effective)    │
├─────────────────────────────────────┤     ├─────────────────────────────────────┤
│  • Reviews Solana program design    │     │  • Receives orchestrator prompt     │
│  • Creates implementation plan      │     │  • Executes ONE milestone only      │
│  • Validates security checklist     │────▶│  • Runs anchor test / cargo test    │
│  • Writes orchestrator prompt       │◀────│  • Generates progress report        │
│  • Validates milestone reports      │     │  • STOPS and waits for approval     │
│  • Approves/rejects milestones      │     │                                     │
│  • Checks for Solana vulnerabilities│     │  (fresh context each milestone)     │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

### Benefits

| Benefit | Description |
|---------|-------------|
| **Security focus** | Planner validates security at each gate, not just at end |
| **Context efficiency** | Planner stays lean, doesn't accumulate execution details |
| **Model optimization** | Expensive model for security review, cheaper for implementation |
| **Fresh executor** | Each milestone starts clean, no accumulated confusion |

### Planner/Reviewer Responsibilities

1. **Research phase**
   - Review existing Solana program patterns
   - Identify account structures and PDAs
   - Understand SPL token integrations
   - Ask clarifying questions about tokenomics/mechanics

2. **Planning phase**
   - Create implementation plan (`DOC_{feature}_plan.md`)
   - Define milestones with clear deliverables
   - Specify security requirements per milestone
   - Write orchestrator prompt for executor

3. **Review phase**
   - Validate executor's progress report
   - Run security checklist for the milestone
   - Verify tests pass (`anchor test` or `cargo test`)
   - Check for common Solana vulnerabilities
   - Approve, request changes, or abort

### Executor Responsibilities

1. Receive orchestrator prompt with plan reference
2. Execute **ONE milestone only**
3. Run all tests and include output in report
4. Generate progress report in specified format
5. **STOP** and wait for approval
6. Never proceed to next milestone without explicit approval

---

## Response Format Tags (orchestrator-auto compatible)

### Planner Tags

| Tag | Usage |
|-----|-------|
| `[PLAN_READY]` | Plan document created, ready for execution |
| `[PLAN_CONTENT]...[/PLAN_CONTENT]` | Wraps the plan content for parsing |
| `[MILESTONE_APPROVED]` | Milestone approved, proceed to next |
| `[CHANGES_REQUESTED]` | Milestone needs changes, executor should revise |
| `[HUMAN_INPUT_NEEDED]` | Blocker, need human clarification |

### Executor Tags

| Tag | Usage |
|-----|-------|
| `[PROGRESS_REPORT]...[/PROGRESS_REPORT]` | Milestone completion report |
| `[CLARIFICATION_NEEDED]` | Need planner clarification |
| `[BLOCKED]` | Blocked by external dependency |

---

## Handoff Format (Planner → Executor)

The planner creates this prompt to send to a fresh executor session:

```markdown
## Agent Task: [Feature Name]

### Plan Document
Read and follow: `docs/[path]/DOC_[feature]_plan.md`

### Workflow Instructions
This task has **[N] milestones**. After completing each:
1. **STOP** and generate a progress report
2. **WAIT** for approval before proceeding
3. **DO NOT** continue without explicit approval

### Network Configuration
- Development: localnet (solana-test-validator)
- Testing: devnet (https://api.devnet.solana.com)
- Production: mainnet-beta (after full audit)

### Current Milestone: [N]
[Copy milestone details from plan]

### Progress Report Format
```
[PROGRESS_REPORT]
## Milestone [N]: [Name] - COMPLETED

### Files Created/Modified:
- programs/[name]/src/lib.rs (created|modified)
- programs/[name]/src/instructions/[file].rs (created)
- tests/[name].ts (created|modified)

### Test Results:
```
[paste anchor test or cargo test output]
```

### Security Checklist:
- [ ] Signer verification on all privileged instructions
- [ ] PDA seeds validated and bump stored
- [ ] Account ownership checks
- [ ] No unchecked arithmetic (use checked_* or saturating_*)
- [ ] Proper error handling with custom errors

### Notes/Issues:
[blockers, deviations, questions]

### Ready for Review: YES
[/PROGRESS_REPORT]
```

**Begin Milestone [N]. Stop and report when complete.**
```

---

## Solana Plan Document Template

```markdown
# [Feature Name] - Solana Implementation Plan

## 1. Overview
[What program/feature and why - 2-3 sentences]

## 2. Program Specification

### 2.1 Program Details
| Property | Value |
|----------|-------|
| **Program ID** | `[PublicKey or TBD]` |
| **Framework** | Anchor / Native |
| **Cluster** | Devnet → Mainnet |
| **Dependencies** | anchor-lang, anchor-spl, mpl-token-metadata |

### 2.2 Account Structures
```rust
#[account]
pub struct [StateName] {
    pub authority: Pubkey,      // 32 bytes
    pub data: u64,              // 8 bytes
    pub bump: u8,               // 1 byte
}
// Space: 8 (discriminator) + 32 + 8 + 1 = 49 bytes
```

### 2.3 PDA Derivations
| PDA | Seeds | Usage |
|-----|-------|-------|
| `state` | `["state", authority]` | Global state account |
| `user_account` | `["user", user_pubkey]` | Per-user data |
| `vault` | `["vault", state]` | Token vault |

### 2.4 Instructions
| Instruction | Accounts | Args | Description |
|-------------|----------|------|-------------|
| `initialize` | authority (signer), state (init), system_program | None | Initialize program state |
| `deposit` | user (signer), user_account, vault, token_program | amount: u64 | Deposit tokens |
| `withdraw` | user (signer), user_account, vault, token_program | amount: u64 | Withdraw tokens |

### 2.5 Events (Optional)
```rust
#[event]
pub struct DepositEvent {
    pub user: Pubkey,
    pub amount: u64,
    pub timestamp: i64,
}
```

### 2.6 Error Codes
```rust
#[error_code]
pub enum [ProgramName]Error {
    #[msg("Insufficient funds")]
    InsufficientFunds,
    #[msg("Invalid authority")]
    InvalidAuthority,
    #[msg("Arithmetic overflow")]
    Overflow,
}
```

## 3. Architecture

### 3.1 File Structure (Anchor)
```
programs/[program-name]/
├── Cargo.toml
├── Xargo.toml
└── src/
    ├── lib.rs              # Program entrypoint + instruction routing
    ├── state/
    │   ├── mod.rs
    │   └── [state].rs      # Account structures
    ├── instructions/
    │   ├── mod.rs
    │   ├── initialize.rs
    │   ├── deposit.rs
    │   └── withdraw.rs
    ├── errors.rs           # Custom error codes
    └── events.rs           # Event definitions

tests/
├── [program-name].ts       # Integration tests
└── utils/
    └── helpers.ts          # Test utilities

app/                        # Optional client SDK
├── src/
│   ├── index.ts
│   ├── instructions.ts
│   └── accounts.ts
└── package.json
```

### 3.2 Patterns to Follow
- Instruction: `programs/[existing]/src/instructions/[file].rs`
- State: `programs/[existing]/src/state/[file].rs`
- Tests: `tests/[existing].ts`

## 4. Security Considerations

### 4.1 Required Checks (Every Instruction)
- [ ] Verify all signers
- [ ] Validate account ownership (program owns what it should)
- [ ] Check PDA derivations match expected seeds
- [ ] Use `require!()` or `require_keys_eq!()` for all constraints
- [ ] Handle all arithmetic with checked/saturating operations

### 4.2 Specific Vulnerabilities to Avoid
| Vulnerability | Mitigation |
|---------------|------------|
| Missing signer check | `Signer<'info>` type or manual `is_signer` check |
| Missing owner check | `Account<'info, T>` validates owner, or manual check |
| PDA substitution | Verify seeds + bump in instruction |
| Integer overflow | `checked_add()`, `checked_mul()`, `saturating_*` |
| Reentrancy | State updates before CPI calls |
| Rent drain | Close accounts properly with `close = destination` |
| Type cosplay | Use discriminators (Anchor handles automatically) |

### 4.3 CPI Security (if applicable)
- [ ] Validate CPI target program ID
- [ ] Sign with correct PDA seeds
- [ ] Check return values

## 5. Testing Strategy

### 5.1 Unit Tests (Rust)
```bash
cargo test --manifest-path programs/[name]/Cargo.toml
```
- test_[instruction]_success
- test_[instruction]_invalid_signer
- test_[instruction]_insufficient_funds

### 5.2 Integration Tests (TypeScript)
```bash
anchor test
```
- test full user flow (init → deposit → withdraw)
- test error conditions
- test edge cases (zero amounts, max amounts)

### 5.3 Coverage Targets
| Component | Target |
|-----------|--------|
| Instructions | 90% |
| State validation | 95% |
| Error paths | 80% |

## 6. Deployment Strategy

### 6.1 Localnet
```bash
solana-test-validator
anchor deploy --provider.cluster localnet
```

### 6.2 Devnet
```bash
solana airdrop 2 --url devnet
anchor deploy --provider.cluster devnet
anchor idl init --filepath target/idl/[name].json [PROGRAM_ID] --provider.cluster devnet
```

### 6.3 Mainnet (After Audit)
```bash
anchor deploy --provider.cluster mainnet
anchor idl init --filepath target/idl/[name].json [PROGRAM_ID] --provider.cluster mainnet
```

## 7. Milestones

### Milestone 1: Project Setup + Account Structures
**Deliverables:**
- [ ] Anchor project initialized with correct dependencies
- [ ] All account structures defined with space calculations
- [ ] PDA derivation logic implemented
- [ ] Error codes defined
- [ ] Basic project compiles: `anchor build`

### Milestone 2: Core Instructions
**Deliverables:**
- [ ] All instruction handlers implemented
- [ ] Context structs with proper constraints
- [ ] Events emitted where appropriate
- [ ] Compiles without warnings

### Milestone 3: Comprehensive Tests
**Deliverables:**
- [ ] Unit tests for all instructions
- [ ] Integration tests covering happy paths
- [ ] Error condition tests
- [ ] `anchor test` passes 100%

### Milestone 4: Security Audit + Devnet
**Deliverables:**
- [ ] Security checklist completed (Section 4)
- [ ] Code review for common vulnerabilities
- [ ] Deployed to devnet
- [ ] IDL published to devnet
- [ ] Manual testing on devnet successful

### Milestone 5: Documentation + Client SDK (Optional)
**Deliverables:**
- [ ] README with usage instructions
- [ ] TypeScript client SDK
- [ ] Example transactions
- [ ] Deployment runbook

## 8. Anti-Patterns

### Don't: Unchecked Arithmetic
```rust
// BAD
let total = balance + amount;  // Can overflow!
```

### Do: Checked Arithmetic
```rust
// GOOD
let total = balance.checked_add(amount).ok_or(ErrorCode::Overflow)?;
```

### Don't: Missing Signer Verification
```rust
// BAD - Anyone can call!
pub fn withdraw(ctx: Context<Withdraw>, amount: u64) -> Result<()> {
    // No signer check
}
```

### Do: Explicit Signer
```rust
// GOOD
#[derive(Accounts)]
pub struct Withdraw<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,  // Must sign
    #[account(mut, has_one = authority)]
    pub vault: Account<'info, Vault>,
}
```
```

---

## Orchestrator Prompt Template (Solana)

```markdown
## Agent Task: [Task Title]

### Objective
[One-sentence description]

### Context
[2-3 sentences: what Solana program, what it connects to, why needed]

### Workflow Instructions
This task has **[N] milestones**. After each:
1. **STOP** and generate a progress report
2. **WAIT** for approval
3. **DO NOT** proceed until explicitly approved

### Network
- Localnet for development/tests
- Devnet for deployment milestone

---

## Milestone [N]: [Name]

### Prerequisites
- [Previous milestone approved, if applicable]
- [Anchor CLI installed, Solana CLI configured]

### Tasks
1. [Task]
2. [Task]

### Key References
- [Existing program pattern to follow]
- [SPL program documentation if needed]

### Deliverables
- [ ] [Deliverable]
- [ ] `anchor build` succeeds
- [ ] `anchor test` passes

### Security Checklist for This Milestone
- [ ] All signers verified
- [ ] PDA seeds validated
- [ ] No unchecked arithmetic

**STOP - Generate progress report, wait for approval**

---

[Repeat milestone block for each milestone]

---

## Quick Reference

| Resource | Path |
|----------|------|
| Implementation Plan | `docs/path/to/plan.md` |
| Pattern to Follow | `programs/existing/src/instructions/example.rs` |
| Anchor Docs | https://www.anchor-lang.com/ |
```

---

## Progress Report Template (Solana)

Use this format after completing each milestone:

```
[PROGRESS_REPORT]
## Milestone [N]: [Name] - COMPLETED

### Files Created/Modified:
- programs/[name]/src/lib.rs (modified)
- programs/[name]/src/instructions/[file].rs (created)
- programs/[name]/src/state/[file].rs (created)
- tests/[name].ts (modified)

### Build Output:
```
anchor build
# [paste output showing successful build]
```

### Test Results:
```
anchor test
# [paste full test output]
```

### Security Checklist:
- [x] Signer verification: All privileged instructions require signer
- [x] PDA validation: Seeds and bumps verified
- [x] Arithmetic: Using checked_* operations
- [x] Owner checks: Account ownership validated
- [ ] CPI security: N/A for this milestone

### Notes/Issues:
[blockers, deviations, questions]

### Ready for Review: YES
[/PROGRESS_REPORT]
```

For final milestone, add:
```
### Devnet Deployment:
- Program ID: `[PublicKey]`
- IDL Published: Yes
- Explorer: https://explorer.solana.com/address/[PublicKey]?cluster=devnet

### TASK COMPLETE - Ready for Final Review
```

---

## Review Commands

| Action | Command |
|--------|---------|
| **Approve** | `Milestone [N] approved. Proceed to Milestone [N+1].` |
| **Changes needed** | `Milestone [N] needs changes: [issues]. Fix and regenerate report.` |
| **Security concern** | `Milestone [N] has security issues: [vulnerabilities]. Address before proceeding.` |
| **Approve with notes** | `Milestone [N] approved with notes: [observations]. Proceed.` |
| **Abort** | `ABORT: [Reason]. Do not proceed.` |

---

## Kickstart Prompts (Copy-Paste)

### Reviewer Agent (First Claude Session)

```
Read CLAUDE_orch_solana.md. You are the REVIEWER agent for Solana development.

Create an implementation plan for: [SOLANA PROGRAM DESCRIPTION]

1. Research the codebase to understand existing Anchor patterns
2. Create plan at: docs/[feature]/DOC_[feature]_plan.md
3. Define 3-5 milestones with clear deliverables and security requirements
4. Generate the executor prompt for Milestone 1

After creating the plan, show me the prompt to send to the executor agent.
```

### Executor Agent (Second Claude Session)

```
Read CLAUDE_orch_solana.md. You are the EXECUTOR agent for Solana development.

[PASTE PROMPT FROM REVIEWER AGENT]
```

### Reviewer: Continue After Milestone Approval

```
Milestone [N] approved.

Generate the prompt for the executor to continue with Milestone [N+1].
```

### Reviewer: Security Concerns

```
Milestone [N] has security issues:
- [Vulnerability 1]
- [Vulnerability 2]

Generate a prompt for the executor to fix these security issues.
```

---

## Typical Session Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SOLANA TWO-SESSION WORKFLOW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SESSION 1: REVIEWER                    SESSION 2: EXECUTOR                  │
│  ─────────────────────                  ────────────────────                 │
│                                                                              │
│  1. "Create plan for staking program"                                        │
│     ↓                                                                        │
│  2. Creates DOC_staking_plan.md                                              │
│     ↓                                                                        │
│  3. Outputs executor prompt ──────────► 4. Receives prompt                   │
│                                            ↓                                 │
│                                         5. Executes M1 (setup + state)       │
│                                            ↓                                 │
│  6. Reviews progress report ◄─────────── 6. Reports + STOPS                  │
│     ↓                                                                        │
│  7. Security checklist ✓                                                     │
│     ↓                                                                        │
│  8. "Approved, generate M2 prompt" ───► 9. Continues with M2 (instructions)  │
│     ↓                                      ↓                                 │
│  [Repeat until all milestones done]                                          │
│     ↓                                      ↓                                 │
│  10. Final security audit            ── 10. Devnet deployment                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Solana Security Checklist (Reviewer Reference)

### Per-Milestone Validation

| Check | Question |
|-------|----------|
| **Signers** | Are all privileged operations protected by signer checks? |
| **PDAs** | Are seeds deterministic and bumps stored/validated? |
| **Ownership** | Does program verify it owns accounts it modifies? |
| **Arithmetic** | All math using checked/saturating operations? |
| **Reentrancy** | State updated before any CPI calls? |
| **Rent** | Accounts closed properly, rent returned? |
| **Discriminators** | Using Anchor or manual discriminators to prevent type confusion? |

### Pre-Devnet Checklist

| Check | Verified |
|-------|----------|
| All instructions reviewed for access control | [ ] |
| No hardcoded keys (use PDAs or passed accounts) | [ ] |
| Error messages don't leak sensitive info | [ ] |
| Upgrade authority properly configured | [ ] |
| IDL matches actual program | [ ] |

### Pre-Mainnet Checklist

| Check | Verified |
|-------|----------|
| Professional security audit completed | [ ] |
| All audit findings addressed | [ ] |
| Upgrade authority is multisig or frozen | [ ] |
| Emergency pause mechanism (if applicable) | [ ] |
| Monitoring/alerting configured | [ ] |

---

## Git Checkpoint Strategy

### When to Commit

| Event | Who Commits | Message Format |
|-------|-------------|----------------|
| After milestone approved | Executor | `feat(solana/[program]): complete M[N] - [description]` |
| Before risky change | Executor | `chore(solana/[program]): checkpoint before [risky thing]` |
| End of session | Executor | `wip(solana/[program]): M[N] in progress - [status]` |

### Commit Message Examples

```bash
# After milestone approval
feat(solana/staking): complete M1 - account structures and PDAs
feat(solana/staking): complete M2 - stake and unstake instructions
feat(solana/staking): complete M3 - comprehensive test suite
feat(solana/staking): complete M4 - devnet deployment

# Work in progress
wip(solana/staking): M2 in progress - stake done, unstake pending

# Checkpoint
chore(solana/staking): checkpoint before CPI integration
```

---

## Recovery Protocol

### If Reviewer Session Crashes

**Start new Reviewer session with:**

```
Read CLAUDE_orch_solana.md. You are the REVIEWER agent.

Recovering session for: [PROGRAM NAME]

Plan document: docs/[feature]/DOC_[feature]_plan.md

Current status:
- Milestones approved: [1, 2, ...]
- Current milestone: [N] (executor working / awaiting review)
- Security issues found: [None / description]
- Blocking issues: [None / description]

[If executor submitted report, paste it here]

Continue reviewing from where we left off.
```

### If Executor Session Crashes

**Start new Executor session:**

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
Run `anchor build` and `anchor test` before generating progress report.
Stop and report when milestone is complete.
```

---

## Common Solana Development Commands

### Anchor Commands
```bash
# Initialize new project
anchor init [project-name]

# Build program
anchor build

# Run tests
anchor test

# Deploy to cluster
anchor deploy --provider.cluster [localnet|devnet|mainnet]

# Publish IDL
anchor idl init --filepath target/idl/[name].json [PROGRAM_ID] --provider.cluster [cluster]

# Upgrade program
anchor upgrade target/deploy/[name].so --program-id [PROGRAM_ID] --provider.cluster [cluster]
```

### Solana CLI Commands
```bash
# Start local validator
solana-test-validator

# Check balance
solana balance --url [cluster]

# Airdrop (devnet only)
solana airdrop 2 --url devnet

# Get program info
solana program show [PROGRAM_ID] --url [cluster]

# View account
solana account [PUBKEY] --url [cluster]
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12 | Initial Solana framework based on CLAUDE_orchestrator.md v2.3 |
