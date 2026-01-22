// Shared constants and types for Supabase integration

export const SESSION_COOKIE_NAME = "user_session_id";

export type CookieToSet = {
  name: string;
  value: string;
  options?: Record<string, unknown>;
};
