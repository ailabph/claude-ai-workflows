# Wheel Game (Bonus Draw) - Implementation Plan

> **Status**: Ready for Execution
> **Date**: 2024-12-31
> **Workflow**: Orchestrator v2 (Gated Milestones)

---

## 1. Overview

A spin-the-wheel mini-game ("Bonus Draw") that uses casino psychology to drive user engagement. Users earn spins through high-value actions (referrals, deposits, swaps) and win rewards (points, vouchers, extra spins, jackpot). This is an MVP implementation with tiered wheels planned for Phase 2.

---

## 2. Specification

### 2.1 MVP Scope

| Feature | Included | Notes |
|---------|----------|-------|
| Spin wheel | ✅ | CSS animation, server-determined outcome |
| Points rewards | ✅ | 50/100/200/500/1000 pts |
| Swap Bonus voucher | ✅ | +50 pts on next swap verification |
| Deposit Bonus voucher | ✅ | +100 pts on next deposit verification |
| Extra Spin | ✅ | +1 spin on win |
| Jackpot badge | ✅ | `badge_awarded: true` in response |
| Near-miss animation | ✅ | Feature-flagged, default ON |
| Tiered wheels | ❌ | Phase 2 |

### 2.2 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/lucky-draw/status/` | Get available spins, wheel config |
| POST | `/api/v1/lucky-draw/spin/` | Execute spin, return outcome |
| GET | `/api/v1/lucky-draw/vouchers/` | User's active vouchers |
| GET | `/api/v1/lucky-draw/history/` | Past spin results |

### 2.3 Spin Earning Events

| Event | Spins | Integration Point |
|-------|-------|-------------------|
| Own swap verification | +1 | `SwapVerifyView.post()` |
| Own deposit verification | +1 | `DepositVerifyView.post()` |
| Referral signup | +1 | `Referral` post_save signal |
| Referral links Coinsher | +2 | `CoinsherLink` post_save signal |

---

## 3. Architecture

### 3.1 Backend File Structure

```
backend/apps/lucky_draw/
├── __init__.py
├── admin.py
├── apps.py
├── models.py          # LuckyDrawBalance, LuckyDrawSpin, UserVoucher
├── constants.py       # WHEEL_SEGMENTS, VOUCHER_EXPIRY, SPIN_AWARDS
├── services.py        # LuckyDrawService
├── serializers.py     # DRF serializers
├── views.py           # API views
├── urls.py            # URL routing
├── signals.py         # Referral spin awards
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_services.py
    ├── test_views.py
    └── test_signals.py
```

### 3.2 Frontend File Structure

```
frontend/src/
├── types/luckyDraw.ts
├── pages/LuckyDrawPage.tsx
├── components/lucky-draw/
│   ├── LuckyDrawWheel.tsx
│   ├── SpinResultModal.tsx
│   ├── VouchersList.tsx
│   └── index.ts
└── services/
    ├── api.ts           # Add methods
    └── mockData.ts      # Add mock data
```

### 3.3 Patterns to Follow

| Pattern | Example Location |
|---------|------------------|
| Django App | `backend/apps/rewards/` |
| Service Layer | `backend/apps/rewards/services.py` |
| API Views | `backend/apps/users/views.py` |
| PointTransaction | `backend/apps/rewards/models.py` (field: `points`, type: `TransactionType.BONUS`) |
| Verify View Flow | `backend/apps/users/views.py:328-360` (SwapVerifyView) |
| Frontend Page | `frontend/src/pages/TasksPage.tsx` |
| API Client | `frontend/src/services/api.ts` |

---

## 4. Critical Implementation Rules

> **READ BEFORE IMPLEMENTING** - Violations will cause bugs.

### 4.1 Idempotency: Spin Awards (HIGH)

**Problem**: Verify endpoints can be called multiple times. Awarding spins on every "success" = infinite spins.

**Rule**: Award spins ONLY when NEW `TaskCompletion` is created.

```python
# CORRECT - Inside transaction.atomic(), after TaskCompletion.objects.create():
with transaction.atomic():
    completion = TaskCompletion.objects.create(...)  # NEW completion
    user.total_points += points_to_award
    user.save()
    PointTransaction.objects.create(...)

    # Award spin HERE - inside atomic, after new completion
    LuckyDrawService.award_spins(user, count=1, source='swap_verify')

# NEVER award in the "existing_completion" early-return branch
```

### 4.2 Signal Guards (HIGH)

**Problem**: `post_save` fires on create AND update. No guard = duplicate spins.

**Rule**: Always check `created=True`:

```python
@receiver(post_save, sender=Referral)
def award_spin_for_referral(sender, instance, created, **kwargs):
    if not created:  # CRITICAL
        return
    if instance.referrer:
        LuckyDrawService.award_spins(...)
```

### 4.3 PointTransaction Pattern (MEDIUM)

**Rule**: Use existing conventions:

```python
from apps.rewards.models import PointTransaction, TransactionType

PointTransaction.objects.create(
    user=user,
    transaction_type=TransactionType.BONUS,  # Not a new type
    points=points_awarded,                    # Field is 'points', not 'amount'
    description=f"Lucky Draw: {outcome['label']}"
)
```

### 4.4 App Creation Command

```bash
cd backend
python manage.py startapp lucky_draw apps/lucky_draw
```

---

## 5. Anti-Patterns

### Don't: Award spins on any success response
```python
# BAD - awards on repeat calls
def post(self, request):
    if verify_swap():
        LuckyDrawService.award_spins(user, 1, 'swap')  # WRONG LOCATION
        return Response({"success": True})
```

### Do: Award only on new completion creation
```python
# GOOD - idempotent
def post(self, request):
    existing = TaskCompletion.objects.filter(...).first()
    if existing:
        return Response({"already_completed": True})  # No spin here

    with transaction.atomic():
        TaskCompletion.objects.create(...)
        LuckyDrawService.award_spins(user, 1, 'swap')  # Only here
```

---

## 6. Testing Strategy

### 6.1 Unit Tests
- Model creation and properties
- Service methods (weighted random, rotation calculation)
- Voucher expiry logic

### 6.2 Integration Tests
- API endpoints (auth, success, error cases)
- Signal handlers (with idempotency verification)
- Verify view integration (repeat call doesn't duplicate)

### 6.3 Critical Idempotency Tests
- `test_swap_verify_does_not_award_spin_on_repeat_call`
- `test_deposit_verify_does_not_award_spin_on_repeat_call`
- `test_referral_update_does_not_award_spin`
- `test_coinsher_link_update_does_not_award_spin`

### 6.4 Coverage Targets

| Component | Target |
|-----------|--------|
| Models | 90% |
| Services | 85% |
| Views | 80% |
| Frontend Components | 75% |

---

## 7. Milestones

This implementation has **5 milestones**. After completing each:
1. **STOP** and generate a progress report
2. **WAIT** for approval before proceeding
3. **DO NOT** continue without explicit approval

| # | Name | Est. Time |
|---|------|-----------|
| M1 | Backend Foundation | 3-4h |
| M2 | Backend Core Logic | 3-4h |
| M3 | Backend API & Integration | 3-4h |
| M4 | Frontend Foundation | 3-4h |
| M5 | Frontend Polish & Integration | 2-3h |

---

### Milestone 1: Backend Foundation

### Prerequisites
- None (first milestone)

### Tasks
1. Create app: `python manage.py startapp lucky_draw apps/lucky_draw`
2. Create models (`models.py`):
   - `LuckyDrawBalance`: user spin balance
   - `LuckyDrawSpin`: spin audit trail
   - `UserVoucher`: vouchers won
3. Create constants (`constants.py`):
   - `WHEEL_SEGMENTS`: 8 segments with weights
   - `VOUCHER_EXPIRY`: expiry durations
   - `SPIN_AWARDS`: spin counts per event
4. Create app config (`apps.py`) with signal import in `ready()`
5. Register app in `config/settings.py`:
   - Add to `INSTALLED_APPS`
   - Add `WHEEL_NEAR_MISS_ENABLED`, `WHEEL_NEAR_MISS_RATE` settings
6. Create and apply migrations
7. Create admin registrations (`admin.py`)
8. Create basic service methods (`services.py`):
   - `get_or_create_balance(user)`
   - `award_spins(user, count, source)`
9. Create model tests (`tests/test_models.py`)

### Key References
- Models: `WHEEL_GAME_IMPL_PLAN.md` lines 171-298
- Constants: `WHEEL_GAME_IMPL_PLAN.md` lines 300-335
- Existing app pattern: `backend/apps/rewards/`

### Deliverables
- [ ] `apps/lucky_draw/` directory with all files
- [ ] 3 models defined and migrated
- [ ] Constants defined
- [ ] App registered with feature flags
- [ ] Basic service methods implemented
- [ ] Model tests passing

### Test Command
```bash
pytest apps/lucky_draw/tests/test_models.py -v
```

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 2: Backend Core Logic

### Prerequisites
- Milestone 1 approved

### Tasks
1. Implement weighted random selection (`_weighted_random_outcome`)
2. Implement near-miss logic:
   - `_should_near_miss()`: check flag and probability
   - `_calculate_rotation()`: rotation degrees with near-miss
3. Implement `execute_spin(user)`:
   - Balance check with `select_for_update`
   - Outcome determination
   - Reward processing (points/voucher/extra_spin/jackpot)
   - PointTransaction creation (use `TransactionType.BONUS`, field `points`)
   - Spin record creation
4. Implement `apply_voucher_if_applicable(user, voucher_type)`:
   - `select_for_update` to prevent double consumption
   - Mark voucher used, award bonus points
5. Implement helpers:
   - `get_user_vouchers(user, active_only)`
   - `get_wheel_config()`
6. Create service tests (`tests/test_services.py`):
   - `test_award_spins_creates_balance`
   - `test_execute_spin_decrements_balance`
   - `test_execute_spin_no_spins_raises`
   - `test_execute_spin_awards_points`
   - `test_execute_spin_creates_voucher`
   - `test_extra_spin_increments_balance`
   - `test_voucher_consumption`
   - `test_expired_voucher_not_consumed`

### Key References
- Execute spin: `WHEEL_GAME_IMPL_PLAN.md` lines 467-611
- Voucher consumption: `WHEEL_GAME_IMPL_PLAN.md` lines 625-674
- PointTransaction pattern: `backend/apps/rewards/models.py`

### Deliverables
- [ ] `services.py` fully implemented
- [ ] Weighted random selection working
- [ ] Near-miss rotation calculation working
- [ ] `execute_spin()` handles all reward types
- [ ] Voucher consumption with race safety
- [ ] 8+ service tests passing

### Test Command
```bash
pytest apps/lucky_draw/tests/test_services.py -v
```

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 3: Backend API & Integration

### Prerequisites
- Milestone 2 approved

### Tasks
1. Create serializers (`serializers.py`):
   - `LuckyDrawBalanceSerializer`
   - `LuckyDrawStatusSerializer`
   - `SpinResultSerializer`
   - `UserVoucherSerializer`
   - `SpinHistorySerializer`
2. Create views (`views.py`):
   - `LuckyDrawStatusView` (GET)
   - `LuckyDrawSpinView` (POST)
   - `LuckyDrawVouchersView` (GET)
   - `LuckyDrawHistoryView` (GET)
   - Use `[TelegramMiniAppAuthentication, DevelopmentAuthentication]`
3. Create URLs (`urls.py`) and register in `config/urls.py`
4. Create signals (`signals.py`) with `created=True` guards:
   ```python
   @receiver(post_save, sender=Referral)
   def award_spin_for_referral(sender, instance, created, **kwargs):
       if not created:
           return
       # award spin...
   ```
5. Integrate with `SwapVerifyView` (idempotent):
   - Add spin award INSIDE `transaction.atomic()`, AFTER `TaskCompletion.objects.create()`
   - Add voucher consumption
6. Integrate with `DepositVerifyView` (same pattern)
7. Create view tests (`tests/test_views.py`)
8. Create signal tests with idempotency (`tests/test_signals.py`):
   - `test_referral_update_does_not_award_spin`
9. Create verify integration tests:
   - `test_swap_verify_does_not_award_spin_on_repeat_call`
   - `test_deposit_verify_does_not_award_spin_on_repeat_call`
10. Verify endpoints appear in Swagger at `/api/docs/`

### Key References
- Serializers: `WHEEL_GAME_IMPL_PLAN.md` lines 711-764
- Views: `WHEEL_GAME_IMPL_PLAN.md` lines 766-861
- SwapVerifyView: `backend/apps/users/views.py:328-360`
- Critical Rules: Section 4 of this document

### Deliverables
- [ ] 5 serializers created
- [ ] 4 API views working
- [ ] URLs registered
- [ ] Signals with `created=True` guards
- [ ] SwapVerifyView integrated (idempotent)
- [ ] DepositVerifyView integrated (idempotent)
- [ ] Idempotency tests proving no duplicate awards
- [ ] All backend tests passing
- [ ] Endpoints visible in Swagger

### Test Commands
```bash
pytest apps/lucky_draw/ -v
pytest apps/users/tests/ -k "swap_verify or deposit_verify" -v
```

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 4: Frontend Foundation

### Prerequisites
- Milestone 3 approved
- Backend API endpoints working

### Tasks
1. Create TypeScript types (`types/luckyDraw.ts`):
   - `WheelSegment`, `WheelConfig`
   - `LuckyDrawBalance`, `LuckyDrawStatus`
   - `SpinOutcome`, `SpinAnimation`, `SpinResult`
   - `VoucherData`, `UserVoucher`
2. Add API client methods (`services/api.ts`):
   - `getLuckyDrawStatus()`
   - `spinLuckyDraw()`
   - `getLuckyDrawVouchers(activeOnly)`
3. Add mock data (`services/mockData.ts`):
   - `mockLuckyDrawStatus`
   - `mockSpinLuckyDraw()` with randomized outcomes
4. Create wheel component (`components/lucky-draw/LuckyDrawWheel.tsx`):
   - SVG/CSS wheel with 8 segments
   - Props: `segments`, `isSpinning`, `rotation`, `onSpin`, `disabled`
   - CSS transition: `cubic-bezier(0.17, 0.67, 0.12, 0.99)`, 4s duration
5. Create Lucky Draw page (`pages/LuckyDrawPage.tsx`):
   - Fetch status on mount
   - Display spin count
   - Wheel with spin handler
   - Loading/error states
6. Add route `/lucky-draw`
7. Create component exports (`components/lucky-draw/index.ts`)

### Key References
- Types: `WHEEL_GAME_IMPL_PLAN.md` lines 1012-1075
- API client: `WHEEL_GAME_IMPL_PLAN.md` lines 1077-1115
- Animation: `WHEEL_GAME_SPEC.md` lines 314-340
- Existing page pattern: `frontend/src/pages/TasksPage.tsx`

### Deliverables
- [ ] TypeScript types defined
- [ ] API client methods added
- [ ] Mock data for dev:mock mode
- [ ] LuckyDrawWheel component with animation
- [ ] LuckyDrawPage working
- [ ] Route registered
- [ ] Wheel spins with 4s CSS animation
- [ ] Works in mock mode: `npm run dev:mock`

### Test Command
```bash
npm run dev:mock
# Navigate to /lucky-draw, test spin
```

**⛔ STOP - Generate progress report, wait for approval**

---

### Milestone 5: Frontend Polish & Integration

### Prerequisites
- Milestone 4 approved

### Tasks
1. Create `SpinResultModal`:
   - Different celebrations (small/medium/big/jackpot)
   - Voucher display with expiry countdown
   - Near-miss message ("So close!")
2. Create `VouchersList`:
   - Active vouchers with countdown
   - "Use now" action
   - Empty state
3. Add visual effects:
   - Confetti on win (`canvas-confetti` package)
   - Glow on winning segment
4. Update `LuckyDrawPage`:
   - Integrate result modal
   - Show vouchers list
   - Update balance after spin
5. Add home page entry card (`pages/HomePage.tsx`):
   - "Bonus Draw" card with spin count
   - Link to `/lucky-draw`
6. Add haptic feedback:
   - `impactOccurred('medium')` on spin
   - `notificationOccurred('success')` on win
7. Create tests:
   - `LuckyDrawPage.test.tsx`: loading, render, spin disabled, result modal
   - `LuckyDrawWheel.test.tsx`: renders segments, animation triggers

### Key References
- UI layouts: `WHEEL_GAME_SPEC.md` lines 733-1430
- Visual effects: `WHEEL_GAME_SPEC.md` lines 515-730
- Home entry: `WHEEL_GAME_SPEC.md` lines 1293-1332

### Deliverables
- [ ] SpinResultModal with celebration variants
- [ ] VouchersList with countdown
- [ ] Confetti effect on wins
- [ ] Near-miss visual feedback
- [ ] Home page entry card
- [ ] Haptic feedback
- [ ] Frontend tests passing
- [ ] Full spin flow working end-to-end

### Test Commands
```bash
npm run test
npm run dev  # Full E2E test with backend
```

**⛔ STOP - Generate progress report, TASK COMPLETE**

---

## 8. Progress Report Format

Use after completing each milestone:

```markdown
## Milestone [N]: [Name] - COMPLETED

### Files Created/Modified:
- path/to/file (created|modified)

### Test Results:
[paste pytest/npm test output]

### Notes/Issues:
[blockers, deviations, questions]

### Ready for Review: YES
```

For M5 (final), add:
```markdown
### Coverage Report:
[paste summary]

### TASK COMPLETE - Ready for Final Review
```

---

## 9. Git Checkpoints

| Milestone | Commit Message |
|-----------|----------------|
| M1 | `feat(lucky-draw): M1 - models, constants, basic service` |
| M2 | `feat(lucky-draw): M2 - spin execution and voucher logic` |
| M3 | `feat(lucky-draw): M3 - API endpoints and verify integration` |
| M4 | `feat(lucky-draw): M4 - frontend wheel page` |
| M5 | `feat(lucky-draw): M5 - polish, home integration, tests` |

---

## 10. Quick Reference

| Resource | Path |
|----------|------|
| This Plan | `docs/wheel-game/DOC_wheel_game_plan.md` |
| Feature Spec | `docs/WHEEL_GAME_SPEC.md` |
| Implementation Reference | `docs/WHEEL_GAME_IMPL_PLAN.md` |
| Orchestrator Framework | `CLAUDE_orchestrator.md` |
