# Authentication Flow

This document describes the authentication and access control system for the GAIK Toolkit demo application.

## Overview

The demo uses a two-step access model:

1. **User Registration** - Users sign up and request access. While the request
   is pending they can try the demos on a small trial allowance.
2. **Admin Approval** - An admin approves or rejects the request in `/admin`.
   Approving it e-mails the user that their access is approved.

Anyone can browse the pages; running a demo needs an account.

## User Registration Flow

1. User visits `/sign-up` and provides:
   - Email address (required)
   - Password (required, min 6 characters)
   - Full name (required)
   - Company (optional)
   - Use case description (optional)

2. On submit:
   - A Supabase auth user is created
   - An `access_requests` record is created with status `pending`
   - User is redirected to `/access-pending`

3. `/access-pending` says the request is under review and, with the trial on,
   that they can start testing at once (see "Trial allowance" below)

## Sign In Flow

1. User visits `/sign-in` and enters credentials

2. On successful authentication:
   - If access status is `approved`: redirect to `/` (home)
   - If access status is `pending`: redirect to `/` when the trial is on and the
     e-mail address is confirmed, otherwise to `/access-pending`
   - If access status is `rejected`: sign out and show error

3. A failed sign-in says why when it is not a wrong password
   (`lib/sign-in-errors.ts`): an unconfirmed address, an expired or disabled
   account (Supabase `user_banned`), too many attempts, or the sign-in service
   not answering. Each failure is logged as
   `[auth] sign-in failed: <code> (<status>) for ga***@example.com`, with the
   address masked.

## Running demos

Pages are open to read. `proxy.ts` is the only auth layer in front of the
FastAPI backend: every state-changing request needs a signed-in, approved user
(`lib/api-access.ts`), or a pending one within the trial allowance. Report
Writer, the helpdesk and the AI Act screening have their own route gates with
the same rules.

### Trial allowance

A pending user can run demos at once, counted in Upstash Redis on the server
(`lib/trial.ts`; without Redis the trial is off and pending users wait):

| Variable | Default | What it limits |
| --- | --- | --- |
| `TRIAL_RUNS_PER_DAY` | 30 | Runs one pending user may make per day |
| `TRIAL_RUNS_PER_DAY_TOTAL` | 300 | Runs all pending users together may make per day, the ceiling on what open sign-up can cost |
| `TRIAL_REPORTS` | 1 | Finished reports a pending user may write |
| `TRIAL_HOURS` | 72 | Hours after sign-up the trial lasts; `0` keeps it until approval |

Pending users get the open models only (`lib/model-tier.ts`), whatever their
address: sign-up does not confirm it. A demo page tells them they are on trial
access, how many runs a day they have and for how long. After `TRIAL_HOURS` a
pending account's runs are refused with "Your trial has ended. Running demos
opens when your account is approved." and the page shows view only until an
admin approves it. The time counts from the Supabase account's `created_at`.

### Temporary accounts

Workshop accounts carry `temp_account` and `temp_expires_at` in
`app_metadata`. A pg_cron job runs `public.expire_temp_accounts()` every 15
minutes: an expired account is banned and its request set to `rejected`. Its
next sign-in says the account has expired. To reopen one, clear
`banned_until`, move `temp_expires_at` and set the request back to `approved`.

## Admin Dashboard

### Access

1. Visit `/admin`
2. Enter the admin password (configured via `ADMIN_PASSWORD` env var)
3. Session is stored in an HTTP-only cookie for 8 hours

### Features

- View all access requests, pending first
- Approve a pending request: the user can run demos, and gets the approval
  e-mail when `MAIL_FROM` is set (below)
- Reject a pending request (user cannot run demos)
- Send the approval e-mail again to an approved user
- Report Writer usage per user: reset a counter, or set a user's own limit
- The first wizard's grant (`wizard_access`): its agent has shell tools on the
  demo API server, so grant it only to people you trust
- Logout to end admin session

### Approval e-mail

`lib/mail/approval-email.ts` sends it through CSC's relay
`smtp.pouta.csc.fi:25`, which takes no login and admits Rahti's egress
addresses only, so it cannot be tested from a workstation. It is off while
`MAIL_FROM` is unset, and the Access Requests card says so.

- `MAIL_FROM`: the visible sender, for example `GAIK Toolkit <someone@haaga-helia.fi>`.
- `MAIL_SENDER`: the mailbox the relay checks, which gets the bounces; it
  defaults to `MAIL_FROM`'s address. It must be a real mailbox in a domain whose
  SPF allows CSC: haaga-helia.fi does, gaik.ai does not.
- `MAIL_REPLY_TO`, `SMTP_HOST`, `SMTP_PORT`: optional.

Approving someone already approved sends nothing. A failed send keeps the
approval, the row offers "Send again", and the log has the SMTP code and status
only, never the relay's reply.

### Security

- One shared password, until the demo gets named administrator accounts with the
  organisation's sign-in (planned for after the AI Hackathon, 3 December 2026).
  Until then:
  - The password is compared in constant time.
  - Sign-in attempts are limited: `ADMIN_SIGN_IN_ATTEMPTS` per client address per
    15 minutes (default 5) and `ADMIN_SIGN_IN_ATTEMPTS_TOTAL` for all addresses
    together per hour (default 30), counted in Upstash Redis and, without it, in
    each replica's memory (`lib/admin/sign-in-limit.ts`).
  - Every sign-in and every change an admin makes is logged with a short session
    id (`[admin] set-status user=<id> status=approved session=<id>`), so a change
    can be traced to the sign-in it came from, though not yet to a person.
- Cookie is HTTP-only and secure in production
- The cookie value is **HMAC-signed** (`lib/admin/session.ts`) and carries its own
  expiry, so it cannot be forged client-side. It is signed with
  `ADMIN_SESSION_SECRET` when set, otherwise with a key derived from
  `ADMIN_PASSWORD` with scrypt; the password itself never signs it. Set
  `ADMIN_SESSION_SECRET` in production. Rotating either secret invalidates all
  outstanding admin sessions.
- Every admin server action and admin API route verifies the signature — the
  panel rendering is not the gate.

## Environment Variables

```bash
# Required for auth
NEXT_PUBLIC_SUPABASE_URL=your-project-url
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-anon-key
SUPABASE_SECRET_KEY=your-service-role-key

# Admin dashboard
ADMIN_PASSWORD=your-secure-password
# Signing secret for the admin session cookie. Without it the key is derived
# from ADMIN_PASSWORD.
ADMIN_SESSION_SECRET=a-long-random-string
# Optional: admin sign-in attempts per address per 15 min, and in all per hour
# ADMIN_SIGN_IN_ATTEMPTS=5
# ADMIN_SIGN_IN_ATTEMPTS_TOTAL=30

# Development only (bypasses all auth checks)
BYPASS_AUTH=true
```

## Database access rules

A signed-in user reads only their own `access_requests` row and cannot write the
table: the approval status, `wizard_access`, the report counters and the report
cap are written only by the server with `SUPABASE_SECRET_KEY`. The rules are in
`supabase/access_requests_rules.sql`; run it in the Supabase SQL editor of the
demo project (it is safe to run again). Then check them with a test account
made for this, pending and not an administrator:

```bash
NEXT_PUBLIC_SUPABASE_URL=... NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=... \
ACCESS_CHECK_EMAIL=... ACCESS_CHECK_PASSWORD=... \
bun scripts/check-access-rules.ts
```

It tries to change each server-owned field, add a row and delete the row with the
account's own session, puts back anything that changed, and exits 1 when any
attempt got through.

## Database Schema

The `access_requests` table stores access request information:

```sql
create table access_requests (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) not null,
  email text not null,
  full_name text not null,
  company text,
  use_case text,
  status text default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at timestamp with time zone default now()
);
```

## Development Tips

- Set `BYPASS_AUTH=true` in `.env.local` to skip auth checks during development
- The admin password should be a strong, unique value in production
- Access request statuses are: `pending`, `approved`, `rejected`
