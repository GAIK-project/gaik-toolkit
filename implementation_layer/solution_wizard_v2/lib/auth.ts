// Lightweight dev login without Supabase.
// Enabled when NEXT_PUBLIC_DEV_AUTH=true (.env.local). Off in production,
// where Supabase auth is used normally.

export const DEV_AUTH = process.env.NEXT_PUBLIC_DEV_AUTH === "true";
export const DEV_COOKIE = "gaik_dev_session";
export const DEV_USER = { email: "dev@gaik.local" };
export const DEV_CREDENTIALS = { email: "dev@gaik.local", password: "gaik" };
