# MailPilot PRD

## Original problem statement
Build a full-stack web application called MailPilot — a simple email campaign management tool for non-technical users. Do not implement real email sending, connect an email provider, or use SMTP yet. Focus on product structure, UI, database architecture, authentication, campaign workflow, CSV recipient validation, mandatory mock test email, and explicit bulk-send confirmation.

## Architecture decisions
- React frontend with responsive workspace navigation and FastAPI API.
- MongoDB collections for users, campaigns, recipients, test emails, sending jobs, and usage.
- JWT bearer authentication with server-side password hashing and user ownership filters.
- Mocked delivery state: single mail, test mail, and bulk send are recorded safely without external delivery.
- CSV validation and 500-recipient enforcement happen on the backend.

## Personas
- Non-technical marketing users who need confidence before sending campaigns.
- Workspace owners reviewing campaign status and recipient limits.

## Core requirements
- Account signup/signin, dashboard, single mail, bulk CSV campaign, dedicated test mail, history/status, settings.
- Mandatory test email and explicit confirmation before bulk send.
- Max 500 unique valid recipients per campaign.

## Implemented (2026-02-14)
- JWT signup/login/me, protected workspace routes, campaign ownership.
- Dashboard capacity meter, recent campaign list, responsive sidebar.
- Single/test mail mock APIs and composer pages.
- Bulk CSV upload, deduplication, email validation, preview, test gate, confirmation, and completion flow.
- MongoDB collection architecture and API states.

## Prioritized backlog
- P0: Connect a real email provider after provider choice and credential setup.
- P1: Add campaign editing and saved drafts; add richer recipient CSV column mapping.
- P2: Add delivery analytics, scheduled sends, templates, and team workspaces.

## Remaining next tasks
- Replace mocked delivery with a provider adapter and server-only credentials.
- Add provider delivery callbacks and campaign progress tracking.
- Add password reset and account profile editing.