# MailPilot PRD

## Original problem statement
Build MailPilot — a simple SaaS email campaign management tool for non-technical users. Support single mail, bulk campaigns with CSV upload (max 500 recipients), mandatory test-email gate with explicit confirmation, and a clean workspace UI. Phase 2 replaced mocked delivery with the Resend provider behind an adapter, and adds server-side sending queue, delivery tracking via webhooks, and an unsubscribe/suppression flow.

## Architecture
- React + framer-motion + react-router frontend calling FastAPI backend under `/api`.
- MongoDB collections: users, campaigns, recipients, test_emails, sending_jobs, suppressions.
- JWT bearer auth stored client-side; server-side password hashing (bcrypt).
- Email provider is behind an `EmailProviderAdapter` (mock + Resend). Selection via `EMAIL_PROVIDER` env.
- Bulk sends go through a background queue (`process_job`) with retries, refresh_counts after every recipient, and webhook updates for delivered/bounced/complained/failed.
- Unsubscribe uses HMAC-signed public token so recipients can opt out safely; suppression checked before every marketing send.

## Personas
- Non-technical marketing users who need confidence before sending campaigns.
- Workspace owners reviewing campaign status and recipient limits.

## Core requirements
- Signup/signin, dashboard, single mail, bulk CSV campaign, dedicated test mail, workspace settings.
- Mandatory test email and explicit confirmation before bulk send.
- Max 500 unique valid recipients per campaign (server-side enforced).
- Provider adapter, unsubscribe/suppression, delivery status via webhook.

## Implemented (2026-02-14, refreshed 2026-02-14)
- JWT signup/login/me, protected workspace routes, campaign ownership.
- Dashboard capacity meter, recent campaign list, animated cards, responsive sidebar.
- Single/test mail Resend submissions with clear provider error messages.
- Bulk CSV workflow componentized: Details, Validate, Preview, Test, Confirm, Ready, live Progress.
- Background sending queue with retries, refreshing counts, and campaign COMPLETED state.
- Live progress polling every 2s with animated counters + progress bar.
- Resend webhook mapping including a distinct COMPLAINED status; complaints auto-suppress.
- Public unsubscribe page with HMAC token + suppression enforcement before every send.
- List-Unsubscribe & One-Click headers on marketing sends.
- prefers-reduced-motion respected globally.

## Prioritized backlog
- P1: Domain verification wizard for SENDER_EMAIL and multi-workspace SENDER settings.
- P1: Delivery analytics on the dashboard (bounces, opens if we enable open tracking).
- P2: Scheduled sends, saved templates, per-column CSV mapping.
- P2: Team workspaces and role-based access.

## Remaining next tasks
- Add per-campaign detail view (list recipients with statuses).
- Password reset and profile editing.
