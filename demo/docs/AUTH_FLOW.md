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
   - If access status is `approved`: redirect to `/classifier` (default demo)
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

- Password-protected (simple but effective for demo/internal use)
- No need for separate admin user accounts
- Cookie is HTTP-only and secure in production

## Environment Variables

```bash
# Required for auth
NEXT_PUBLIC_SUPABASE_URL=your-project-url
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-anon-key
SUPABASE_SECRET_KEY=your-service-role-key

# Admin dashboard
ADMIN_PASSWORD=your-secure-password

# Development only (bypasses all auth checks)
BYPASS_AUTH=true
```

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
