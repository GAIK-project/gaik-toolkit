# Authentication Flow

This document describes the authentication and access control system for the GAIK Toolkit demo application.

## Overview

The demo uses a two-step access model:

1. **User Registration** - Users sign up and request access
2. **Admin Approval** - Admins manually approve or reject requests

This ensures only authorized users can access the demo features.

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

3. User receives confirmation that their request is under review

## Sign In Flow

1. User visits `/sign-in` and enters credentials

2. On successful authentication:
   - If access status is `approved`: redirect to `/` (home)
   - If access status is `pending`: redirect to `/access-pending`
   - If access status is `rejected`: sign out and show error

## Protected Routes

The following routes require authentication AND approved access:

- `/classifier` - Document classifier demo
- `/extractor` - Data extractor demo
- `/incident-report` - Incident report demo
- `/parser` - Document parser demo
- `/rag` - RAG (Retrieval-Augmented Generation) demo
- `/transcriber` - Audio transcription demo

Middleware in `lib/supabase/proxy.ts` enforces these protections.

## Admin Dashboard

### Access

1. Visit `/admin`
2. Enter the admin password (configured via `ADMIN_PASSWORD` env var)
3. Session is stored in an HTTP-only cookie for 8 hours

### Features

- View all access requests (pending, approved, rejected)
- Approve pending requests (user can then access demos)
- Reject pending requests (user cannot access demos)
- Logout to end admin session

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
