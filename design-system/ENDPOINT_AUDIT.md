# Endpoint Implementation Audit

> Tracks which API endpoints have been implemented in the frontend services.

## Status Legend

| Status | Meaning |
|--------|---------|
| Implemented | Endpoint has a corresponding service method |
| Partial | Endpoint exists but may need updates |
| Not Implemented | Endpoint documented but not yet in frontend |
| Not Audited | Implementation status not yet verified |

---

## Summary by Domain

| Domain | Total Endpoints | Service File | Status |
|--------|-----------------|--------------|--------|
| [Authentication](#authentication-28-endpoints) | 28 | `authService.ts` | Partial |
| [Balance](#balance-2-endpoints) | 2 | `balanceService.ts` | Implemented |
| [Deposits](#deposits-4-endpoints) | 4 | `depositService.ts` | Partial |
| [Withdrawals](#withdrawals-8-endpoints) | 8 | `withdrawalService.ts` | Partial |
| [Swap](#swap-7-endpoints) | 7 | `swapService.ts` | Partial |
| [Trading](#trading-8-endpoints) | 8 | `spotService.ts` | Not Audited |
| [P2P Trading](#p2p-trading-75-endpoints) | 75 | `p2pService.ts`, `tradeP2PService.ts`, `merchantP2PService.ts`, `merchantService.ts`, `disputeService.ts` | **Audited: 56/75 implemented (75%)** |
| [KYC](#kyc-9-endpoints) | 9 | `kycService.ts` | Not Audited |
| [Notifications](#notifications-12-endpoints) | 12 | `fcmService.ts` | Partial |
| [Assets](#assets-2-endpoints) | 2 | `assetService.ts` | Not Audited |
| [Markets](#markets-8-endpoints) | 8 | `marketsService.ts` | Partial |
| [Fees](#fees-1-endpoint) | 1 | `feesService.ts` | Not Audited |
| [Maintenance](#maintenance-4-endpoints) | 4 | `maintenanceService.ts` | Not Audited |
| [Ramp](#ramp-9-endpoints) | 9 | `transakService.ts` | Partial |
| [TradingView](#tradingview-6-endpoints) | 6 | - | Not Audited |
| [Exchange Admin](#exchange-admin-2-endpoints) | 2 | `exchangeAdminService.ts` | Not Audited |
| [Users](#users-1-endpoint) | 1 | `userProfileService.ts` | Not Audited |
| [Other](#other-19-endpoints) | 19 | - | Not Audited |
| [Web3](#web3-15-chains) | 15 | `web3Service.ts` | Implemented |
| [Market FCM](#market-fcm-2-endpoints) | 2 | `marketFcmService.ts` | Implemented |
| [Telegram](#telegram-8-endpoints) | 8 | - | Not Implemented |

**Total: 230 endpoints** (Updated Dec 2024)

---

## Authentication (28 endpoints)

**Service File:** `services/authService.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/auth/accept-invite/` | GET | Not Audited | - | Accept invitation |
| `/api/v1/auth/change-password` | POST | Not Audited | - | Change password |
| `/api/v1/auth/change-user-rights/` | PUT | Not Audited | - | Admin: Change user rights |
| `/api/v1/auth/check-2fa-status` | POST | Not Audited | - | Check 2FA status |
| `/api/v1/auth/check-role/` | GET | Not Audited | - | Check user role |
| `/api/v1/auth/disable-2FA` | POST | Not Audited | - | Disable 2FA |
| `/api/v1/auth/email-register` | POST | Not Audited | - | Email registration |
| `/api/v1/auth/forgot-password` | POST | Not Audited | - | Forgot password |
| `/api/v1/auth/google` | POST | Not Audited | - | Google OAuth |
| `/api/v1/auth/grant-staff-rights/` | POST | Not Audited | - | Admin: Grant staff rights |
| `/api/v1/auth/login` | POST | Implemented | `emailLogin()` | Login with credentials |
| `/api/v1/auth/logout/` | POST | Not Audited | - | Logout |
| `/api/v1/auth/phone-register` | POST | Not Audited | - | Phone registration |
| `/api/v1/auth/profile` | GET | Implemented | `getProfile()` | Get user profile |
| `/api/v1/auth/referral-list` | GET | Not Audited | - | Get referral list |
| `/api/v1/auth/request-login-otp` | POST | Not Audited | - | Request login OTP |
| `/api/v1/auth/resend-email-otp` | POST | Not Audited | - | Resend email OTP |
| `/api/v1/auth/reset-password` | POST | Not Audited | - | Reset password |
| `/api/v1/auth/send-phone-otp` | POST | Not Audited | - | Send phone OTP |
| `/api/v1/auth/set-country/` | POST | Not Audited | - | Set user country |
| `/api/v1/auth/setup-2fa` | GET | Not Audited | - | Setup 2FA QR code |
| `/api/v1/auth/token/refresh` | POST | Implemented | `refreshToken()` | Refresh JWT token |
| `/api/v1/auth/update-email-or-phone-number` | PUT | Not Audited | - | Update email/phone |
| `/api/v1/auth/update-profile` | PUT | Not Audited | - | Update profile |
| `/api/v1/auth/verify-2fa` | POST | Not Audited | - | Verify 2FA |
| `/api/v1/auth/verify-email-otp` | POST | Not Audited | - | Verify email OTP |
| `/api/v1/auth/verify-phone-otp` | POST | Not Audited | - | Verify phone OTP |
| `/api/v1/auth/verify-updated-email` | POST | Not Audited | - | Verify updated email |

---

## Balance (2 endpoints)

**Service File:** `services/balanceService.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/balance/all/` | GET | Implemented | `getAll()` | Portfolio summary |
| `/api/v1/balance/balance/` | GET | Implemented | `getBalance()` | Specific asset balance |

---

## Deposits (4 endpoints)

**Service File:** `services/depositService.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/deposit/enabled-asset-list/` | GET | Not Audited | - | List deposit assets |
| `/api/v1/deposit/get-address/` | GET | Not Audited | - | Get deposit address |
| `/api/v1/deposit/history/` | GET | Not Audited | - | Deposit history |
| `/api/v1/telegram/verify/deposit/` | GET | Not Implemented | - | Telegram verification |

---

## Withdrawals (8 endpoints)

**Service File:** `services/withdrawalService.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/withdrawal/fee/` | POST | Not Audited | - | Calculate withdrawal fee |
| `/api/v1/withdrawal/history/` | GET | Not Audited | - | Withdrawal history |
| `/api/v1/withdrawal/initiate-email-transfer/` | POST | Not Audited | - | Initiate email transfer |
| `/api/v1/withdrawal/request/` | POST | Not Audited | - | Create withdrawal request |
| `/api/v1/withdrawal/verify-email-transfer/` | POST | Not Audited | - | Verify email transfer |
| `/api/v1/withdrawal/verify/` | POST | Not Audited | - | Verify withdrawal OTP |
| `/api/v1/withdrawal/{withdrawal_id}/details/` | GET | Not Audited | - | Withdrawal details |
| `/api/v1/telegram/verify/withdrawal/` | GET | Not Implemented | - | Telegram verification |

---

## Swap (7 endpoints)

**Service File:** `services/swapService.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/swap/execute/` | GET | Deprecated | - | Use POST instead |
| `/api/v1/swap/execute/` | POST | Not Audited | - | Execute swap |
| `/api/v1/swap/history/` | GET | Not Audited | - | Swap history |
| `/api/v1/swap/list/` | GET | Not Audited | - | Swappable assets |
| `/api/v1/swap/preview/` | GET | Deprecated | - | Use POST instead |
| `/api/v1/swap/preview/` | POST | Not Audited | - | Swap preview |
| `/api/v1/telegram/verify/swap/` | GET | Not Implemented | - | Telegram verification |

---

## Trading (8 endpoints)

**Service File:** `services/spotService.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/trade/cancel-order/` | POST | Not Audited | - | Cancel limit order |
| `/api/v1/trade/create-limit-order-preview/` | POST | Not Audited | - | Preview limit order |
| `/api/v1/trade/create-limit-order/` | POST | Not Audited | - | Create limit order |
| `/api/v1/trade/create-market-order/` | POST | Not Audited | - | Create market order |
| `/api/v1/trade/open-orders/` | GET | Not Audited | - | Get open orders |
| `/api/v1/trade/order-history/` | GET | Not Audited | - | Order history |
| `/api/v1/trade/spot-balance-info/` | GET | Not Audited | - | Spot balance info |
| `/api/v1/trade/trade-history/` | GET | Not Audited | - | Trade history |

---

## P2P Trading (75 endpoints)

**Service Files:** `services/p2pService.ts`, `services/tradeP2PService.ts`, `services/merchantP2PService.ts`, `services/merchantService.ts`, `services/disputeService.ts`

**Audit Summary:** 57 implemented / 75 total (76%)
- Dispute: 7/7 (100%)
- Fiat Currency: 2/7 (29%)
- Merchant: 16/19 (84%) - Updated Dec 2024
- Offer: 13/16 (81%)
- Payment Methods: 6/8 (75%)
- Trade: 11/13 (85%)
- Trade Messages: 5/5 (100%)

### Dispute Endpoints (7/7 implemented)

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/p2p/dispute/` | POST | Implemented | `DisputeService.initiateDispute()` | Create dispute |
| `/api/v1/p2p/dispute/list/` | GET | Implemented | `DisputeService.listAllDisputes()` | List user disputes |
| `/api/v1/p2p/dispute/{dispute_id}/` | GET | Implemented | `DisputeService.getDispute()` | Get dispute details |
| `/api/v1/p2p/dispute/{dispute_id}/message/` | POST | Implemented | `DisputeService.sendMessage()` | Add dispute message |
| `/api/v1/p2p/dispute/{dispute_id}/messages/` | GET | Implemented | `DisputeService.getMessages()` | Get dispute messages |
| `/api/v1/p2p/dispute/{dispute_id}/update/` | PATCH | Partial | `DisputeService.updateDispute()` | Uses POST instead of PATCH |
| `/api/v1/p2p/dispute/{dispute_id}/upload/` | POST | Implemented | `DisputeService.uploadImage()` | Upload dispute evidence |

### Fiat Currency Endpoints (2/7 implemented)

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/p2p/fiat-currency/list` | GET | Implemented | `MerchantP2PService.getFiatCurrencies()` | List fiat currencies |
| `/api/v1/p2p/fiat-currency/market-rate/{code}` | GET | Implemented | `MerchantP2PService.getMarketRate()` | Get market rate |
| `/api/v1/p2p/fiat-currency/user/convert` | POST | Not Implemented | - | Convert currencies |
| `/api/v1/p2p/fiat-currency/user/preferred` | GET | Not Implemented | - | Get preferred fiat |
| `/api/v1/p2p/fiat-currency/user/preferred/set` | PUT | Not Implemented | - | Set preferred fiat |
| `/api/v1/p2p/fiat-currency/user/rates` | GET | Not Implemented | - | Get exchange rates |
| `/api/v1/p2p/fiat-currency/user/view/{code}` | GET | Not Implemented | - | View fiat details |

### Merchant Endpoints (15/19 implemented)

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/p2p/merchant/application/` | GET | Not Implemented | - | Get application (different path in service) |
| `/api/v1/p2p/merchant/application/complete/` | POST | Implemented | `MerchantService.completeApplication()` | Complete application |
| `/api/v1/p2p/merchant/application/id-types/` | GET | Implemented | `MerchantService.getIdTypes()` | Get ID types |
| `/api/v1/p2p/merchant/apply-individual/` | POST | Implemented | `MerchantService.applyIndividual()` | Apply individual |
| `/api/v1/p2p/merchant/apply/` | POST | Implemented | `MerchantService.apply()` | Apply merchant |
| `/api/v1/p2p/merchant/dashboard/` | GET | Implemented | `MerchantP2PService.getMerchantDashboard()` | Merchant dashboard |
| `/api/v1/p2p/merchant/document/submit/` | POST | Implemented | `MerchantService.submitDocument()` | Submit document |
| `/api/v1/p2p/merchant/document/upload/` | POST | Implemented | `MerchantService.uploadDocument()` | Upload document |
| `/api/v1/p2p/merchant/merchant/{offer_id}/overall-stats/` | GET | Implemented | `MerchantP2PService.getMerchantOverallStats()` | Merchant public stats |
| `/api/v1/p2p/merchant/pnl/` | GET | Implemented | `MerchantP2PService.getPnL()` | Merchant PnL |
| `/api/v1/p2p/merchant/profile/display-name/` | GET | Not Implemented | - | Get display name |
| `/api/v1/p2p/merchant/profile/display-name/` | PATCH | Implemented | `MerchantService.patchDisplayName()` | Update display name |
| `/api/v1/p2p/merchant/profile/display-name/history/` | GET | Not Implemented | - | Display name history |
| `/api/v1/p2p/merchant/security-deposit/add/` | POST | Implemented | `MerchantService.addSecurityDeposit()` | Add security deposit |
| `/api/v1/p2p/merchant/security-deposit/history/` | GET | Implemented | `MerchantService.getSecurityDepositHistory()` | Deposit history |
| `/api/v1/p2p/merchant/security-deposit/request-withdrawal/` | POST | Implemented | `MerchantService.securityDepositWithdrawalRequest()` | Request withdrawal |
| `/api/v1/p2p/merchant/security-deposit/status/` | GET | Implemented | `MerchantService.getSecurityDepositStatus()` | Deposit status |
| `/api/v1/p2p/merchant/status/` | GET | Implemented | `MerchantService.getMerchantStatus()` | Merchant status |
| `/api/v1/p2p/merchant/traded-volume/` | GET | Implemented | `MerchantP2PService.getTradedVolume()` | Traded volume |

### Offer Endpoints (13/16 implemented)

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/p2p/offer/allowed-assets/` | GET | Implemented | `UserP2PService.getAllowedAssets()` | Allowed assets |
| `/api/v1/p2p/offer/allowed-assets/` | POST | Not Implemented | - | Update allowed assets (Admin only) |
| `/api/v1/p2p/offer/is-closable/` | GET | Implemented | `MerchantService.offerIsClosable()` | Check if closable |
| `/api/v1/p2p/offer/merchant/own/add/buy` | POST | Implemented | `MerchantP2PService.addBuyOffer()` | Add buy offer |
| `/api/v1/p2p/offer/merchant/own/add/sell` | POST | Implemented | `MerchantP2PService.addSellOffer()` | Add sell offer |
| `/api/v1/p2p/offer/merchant/own/close/{offer_id}/` | DELETE | Implemented | `MerchantP2PService.closeOwnOffer()` | Close offer |
| `/api/v1/p2p/offer/merchant/own/latest-terms/` | GET | Implemented | `MerchantP2PService.getLatestTerms()` | Get latest terms |
| `/api/v1/p2p/offer/merchant/own/list` | GET | Implemented | `MerchantP2PService.getOwnOffers()` | List own offers |
| `/api/v1/p2p/offer/merchant/own/toggle-status/{offer_id}/` | PATCH | Not Implemented | - | Toggle offer status |
| `/api/v1/p2p/offer/merchant/own/update/{offer_id}/` | PUT | Not Implemented | - | Update offer |
| `/api/v1/p2p/offer/merchant/own/view/{offer_id}/` | GET | Implemented | `MerchantP2PService.getOwnOffer()` | View own offer |
| `/api/v1/p2p/offer/merchant/preview/` | POST | Implemented | `MerchantP2PService.previewAd()` | Preview offer |
| `/api/v1/p2p/offer/public/list` | GET | Implemented | `UserP2PService.getAllPublicOffers()` | Public offer list |
| `/api/v1/p2p/offer/public/offer/{offer_id}` | GET | Implemented | `UserP2PService.getPublicOffer()` | View public offer |
| `/api/v1/p2p/offer/{offer_id}/last-seen/` | GET | Implemented | `UserP2PService.getUserStatus()` | Offer owner last seen |
| `/api/v1/p2p/offer/{offer_id}/trade/list/` | GET | Not Implemented | - | Trades for offer |

### Payment Method Endpoints (6/8 implemented)

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/p2p/payment-options/public/available` | GET | Not Implemented | - | Public payment types |
| `/api/v1/p2p/payment-options/user/available-types` | GET | Implemented | `UserP2PService.getAvailablePaymentMethods()` | User payment types |
| `/api/v1/p2p/payment-options/user/payment-method/add` | POST | Implemented | `UserP2PService.addPaymentMethod()` | Add payment method |
| `/api/v1/p2p/payment-options/user/payment-method/delete/{id}` | DELETE | Implemented | `UserP2PService.deletePaymentMethod()` | Delete payment method |
| `/api/v1/p2p/payment-options/user/payment-method/list` | GET | Implemented | `UserP2PService.listPaymentMethod()` | List payment methods |
| `/api/v1/p2p/payment-options/user/payment-method/toggle-activation/{id}` | PUT | Not Implemented | - | Toggle payment method |
| `/api/v1/p2p/payment-options/user/payment-method/update/{id}` | PUT | Implemented | `UserP2PService.updatePaymentMethod()` | Update payment method |
| `/api/v1/p2p/payment-options/user/payment-method/view/{id}` | GET | Implemented | `UserP2PService.viewPaymentMethod()` | View payment method |

### Trade Endpoints (11/13 implemented)

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/p2p/trade/initiate/buy` | POST | Implemented | `TradeP2PService.initiateBuy()` | Initiate buy trade |
| `/api/v1/p2p/trade/initiate/sell` | POST | Implemented | `TradeP2PService.initiateSell()` | Initiate sell trade |
| `/api/v1/p2p/trade/list/` | GET | Implemented | `TradeP2PService.getOwnTrades()` | List user trades |
| `/api/v1/p2p/trade/merchant/own/view/{offer_id}/` | GET | Not Implemented | - | Merchant view offer (duplicate of offer endpoint) |
| `/api/v1/p2p/trade/{offer_id}/check-common-payment-methods` | GET | Implemented | `MerchantP2PService.checkCommonPaymentMethods()` | Check payment methods |
| `/api/v1/p2p/trade/{trade_id}/cancel/` | POST | Implemented | `TradeP2PService.cancelTrade()` | Cancel trade |
| `/api/v1/p2p/trade/{trade_id}/is_disputable/` | GET | Not Implemented | - | Check if disputable |
| `/api/v1/p2p/trade/{trade_id}/release-crypto/` | POST | Implemented | `TradeP2PService.releaseCrypto()` | Release crypto (deprecated) |
| `/api/v1/p2p/trade/{trade_id}/release-crypto/request-otp/` | POST | Implemented | `TradeP2PService.requestOtpReleaseCrypto()` | Request release OTP |
| `/api/v1/p2p/trade/{trade_id}/release-crypto/verify-otp/` | POST | Implemented | `TradeP2PService.releaseCryptoVerifyOtp()` | Verify release OTP |
| `/api/v1/p2p/trade/{trade_id}/upload-proof/` | POST | Implemented | `TradeP2PService.uploadProof()` | Upload proof |
| `/api/v1/p2p/trade/{trade_id}/view-payment/` | GET | Not Implemented | - | View payment proof |
| `/api/v1/p2p/trade/{trade_id}/view/` | GET | Implemented | `TradeP2PService.viewTrade()` | View trade details |

### Trade Message Endpoints (5/5 implemented)

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/p2p/trade_message/user/{trade_id}/history/` | GET | Not Implemented | - | Historical messages |
| `/api/v1/p2p/trade_message/user/{trade_id}/list/` | GET | Implemented | `TradeP2PService.getMessages()` | Trade messages |
| `/api/v1/p2p/trade_message/user/{trade_id}/send/` | POST | Implemented | `TradeP2PService.sendMessage()` | Send message |
| `/api/v1/p2p/trade_message/user/{trade_id}/unread-count/` | GET | Implemented | `TradeP2PService.getUnreadMessageCount()` | Unread count |
| `/api/v1/p2p/trade_message/user/{trade_id}/upload/` | POST | Implemented | `TradeP2PService.uploadMessage()` | Upload image |

### P2P Not Implemented Summary (19 endpoints)

| Category | Endpoint | Notes |
|----------|----------|-------|
| Fiat | `/api/v1/p2p/fiat-currency/user/convert` | Currency conversion |
| Fiat | `/api/v1/p2p/fiat-currency/user/preferred` | Get preferred fiat |
| Fiat | `/api/v1/p2p/fiat-currency/user/preferred/set` | Set preferred fiat |
| Fiat | `/api/v1/p2p/fiat-currency/user/rates` | Exchange rates |
| Fiat | `/api/v1/p2p/fiat-currency/user/view/{code}` | View fiat details |
| Merchant | `/api/v1/p2p/merchant/application/` | Get application |
| Merchant | `/api/v1/p2p/merchant/profile/display-name/` (GET) | Get display name |
| Merchant | `/api/v1/p2p/merchant/profile/display-name/history/` | Display name history |
| Offer | `/api/v1/p2p/offer/allowed-assets/` (POST) | Admin only |
| Offer | `/api/v1/p2p/offer/merchant/own/toggle-status/{offer_id}/` | Toggle offer status |
| Offer | `/api/v1/p2p/offer/merchant/own/update/{offer_id}/` | Update offer |
| Offer | `/api/v1/p2p/offer/{offer_id}/trade/list/` | Trades for offer |
| Payment | `/api/v1/p2p/payment-options/public/available` | Public payment types |
| Payment | `/api/v1/p2p/payment-options/user/payment-method/toggle-activation/{id}` | Toggle activation |
| Trade | `/api/v1/p2p/trade/merchant/own/view/{offer_id}/` | Duplicate endpoint |
| Trade | `/api/v1/p2p/trade/{trade_id}/is_disputable/` | Check disputable |
| Trade | `/api/v1/p2p/trade/{trade_id}/view-payment/` | View payment proof |
| Message | `/api/v1/p2p/trade_message/user/{trade_id}/history/` | Historical messages |

---

## KYC (9 endpoints)

**Service File:** `services/kycService.ts`

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/v1/kyc/country-kyc-docs/` | GET | Not Audited | Country doc types |
| `/api/v1/kyc/country-list/` | GET | Not Audited | Country list |
| `/api/v1/kyc/pending/` | GET | Not Audited | Pending KYC (Admin) |
| `/api/v1/kyc/submit/` | POST | Not Audited | Submit KYC |
| `/api/v1/kyc/v2/status/` | GET | Not Audited | KYC status |
| `/api/v1/kyc/v2/upload-document/` | POST | Not Audited | Upload document |
| `/api/v1/kyc/v2/upload-liveliness/` | POST | Not Audited | Upload liveliness |
| `/api/v1/kyc/v2/upload-personal-info/` | POST | Not Audited | Upload personal info |
| `/api/v1/kyc/v3/document-analysis/` | POST | Not Audited | Document analysis |

---

## Notifications (12 endpoints)

**Service File:** `services/fcmService.ts`

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/v1/notifications/` | GET | Not Audited | List notifications |
| `/api/v1/notifications/fcm/devices/` | GET | Not Audited | FCM devices |
| `/api/v1/notifications/fcm/market-status/` | GET | Not Audited | Market subscription status |
| `/api/v1/notifications/fcm/market-subscribe/` | POST | Not Audited | Subscribe to market updates |
| `/api/v1/notifications/fcm/register/` | POST | Not Audited | Register FCM device |
| `/api/v1/notifications/fcm/test/` | POST | Not Audited | Test notification |
| `/api/v1/notifications/fcm/unregister/` | POST | Not Audited | Unregister FCM device |
| `/api/v1/notifications/mark-all-read/` | POST | Not Audited | Mark all read |
| `/api/v1/notifications/unread-count/` | GET | Not Audited | Unread count |
| `/api/v1/notifications/{notification_id}/` | GET | Not Audited | Get notification |
| `/api/v1/notifications/{notification_id}/delete/` | DELETE | Not Audited | Delete notification |
| `/api/v1/notifications/{notification_id}/mark-read/` | POST | Not Audited | Mark as read |

---

## Markets (8 endpoints)

**Service File:** `services/marketsService.ts`

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/v1/markets/bearish-markets/` | GET | Not Audited | Bearish markets |
| `/api/v1/markets/bullish-markets/` | GET | Not Audited | Bullish markets |
| `/api/v1/markets/info-full/` | GET | Not Audited | Full market info |
| `/api/v1/markets/info/` | GET | Not Audited | Basic market info |
| `/api/v1/markets/kline/` | GET | Not Audited | Candlestick data |
| `/api/v1/markets/order-book/` | GET | Not Audited | Order book |
| `/api/v1/markets/recent-trades/` | GET | Not Audited | Recent trades |
| `/api/v1/markets/top-markets/` | GET | Not Audited | Top markets |

---

## Ramp (9 endpoints)

**Service File:** `services/transakService.ts`

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/v1/ramp/available-asset-to-buy` | GET | Not Audited | Available assets |
| `/api/v1/ramp/available-crypto-currency` | GET | Not Audited | Available crypto |
| `/api/v1/ramp/available-currencies-with-payment-methods/` | GET | Not Audited | Fiat currencies |
| `/api/v1/ramp/buy-data-to-ramp` | GET | Not Audited | Buy data for Ramp |
| `/api/v1/ramp/get-buy-price` | GET | Not Audited | Buy price |
| `/api/v1/ramp/get-kyc-profile` | GET | Not Audited | KYC profile |
| `/api/v1/ramp/get-ramp-order-detail` | GET | Not Audited | Order details |
| `/api/v1/ramp/is-kyc-complete` | GET | Not Audited | KYC status |
| `/api/v1/ramp/update-profile` | PUT | Not Audited | Update profile |

---

## Other Domains

### Assets (2 endpoints)
**Service File:** `services/assetService.ts`

### Fees (1 endpoint)
**Service File:** `services/feesService.ts`

### Maintenance (4 endpoints)
**Service File:** `services/maintenanceService.ts`

### TradingView (6 endpoints)
No dedicated service file.

### Exchange Admin (2 endpoints)
**Service File:** `services/exchangeAdminService.ts`

### Users (1 endpoint)
**Service File:** `services/userProfileService.ts`

### Web3 (15 chains)
**Service File:** `services/web3Service.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| Address validation (implicit) | POST | Implemented | `Web3Service.checkAddress()` | Single chain validation |
| Multi-chain validation | POST | Implemented | `Web3Service.checkMultiChainAddress()` | 15 blockchain support |

**Supported Blockchains:**
- Arbitrum, Base, BNB Chain, Bitcoin, Ethereum, NEAR, Optimism, Polkadot, Polygon, Solana, Stellar, Sui, TON, TRON, XRP Ledger

### Market FCM (2 endpoints)
**Service File:** `services/marketFcmService.ts`

| Endpoint | Method | Status | Service Method | Notes |
|----------|--------|--------|----------------|-------|
| `/api/v1/markets/fcm/subscribe` (implicit) | POST | Implemented | `MarketFcmService.subscribe()` | Subscribe to market updates |
| `/api/v1/markets/fcm/unsubscribe` (implicit) | POST | Implemented | `MarketFcmService.unsubscribe()` | Unsubscribe from market updates |

### Telegram (8 endpoints)
Not implemented - server-side Telegram bot verification.

---

## How to Audit an Endpoint

1. **Open the service file** (e.g., `services/authService.ts`)

2. **Compare documented endpoints** with service methods:
   - Check if endpoint URL matches
   - Check if HTTP method matches
   - Check if request/response types are correct

3. **Update this audit** with implementation status:
   - `Implemented` - Service method exists and is correct
   - `Partial` - Method exists but may need updates
   - `Not Implemented` - No service method exists
   - `Not Audited` - Haven't verified yet

4. **Create missing service methods** as needed

---

## Priority Queue

Endpoints recommended for audit/implementation (based on feature importance):

### High Priority
1. **Authentication** - Core login/registration flows
2. **Balance** - Portfolio display
3. **Deposits/Withdrawals** - Key transaction flows
4. **Markets** - Market data display

### Medium Priority
5. **Swap** - Trading feature
6. **P2P Trading** - P2P marketplace
7. **KYC** - User verification

### Lower Priority
8. **Notifications** - Push notifications
9. **Ramp** - Third-party integration
10. **TradingView** - Chart integration

---

## Service File Reference

| Service File | Primary Domain |
|--------------|----------------|
| `authService.ts` | Authentication, User profile |
| `balanceService.ts` | Balance queries |
| `depositService.ts` | Deposit operations |
| `withdrawalService.ts` | Withdrawal operations |
| `swapService.ts` | Swap operations |
| `spotService.ts` | Spot trading |
| `p2pService.ts` | P2P offers, listings |
| `tradeP2PService.ts` | P2P trade operations |
| `merchantP2PService.ts` | Merchant P2P operations |
| `merchantService.ts` | Merchant application |
| `disputeService.ts` | P2P disputes |
| `kycService.ts` | KYC verification |
| `fcmService.ts` | FCM notifications |
| `assetService.ts` | Asset information |
| `marketsService.ts` | Market data |
| `feesService.ts` | Fee calculations |
| `maintenanceService.ts` | Maintenance mode |
| `transakService.ts` | Ramp/Transak integration |
| `exchangeAdminService.ts` | Admin operations |
| `userProfileService.ts` | User profile operations |
| `web3Service.ts` | Web3 address validation |
| `marketFcmService.ts` | Market data subscriptions |

---

## Related Documentation

- **Endpoint Documentation:** `docs/endpoints/for-users/`
- **Service Files:** `services/`
- **Page Audit:** `docs/design-system/PAGE_AUDIT.md`

---

*Documentation source: Auto-generated from `docs/endpoints/for-users/index.md`*
*To regenerate endpoint docs: `python scripts/refresh_user_docs.py`*
