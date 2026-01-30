import type { ReactNode } from "react";
import { AuthBackdrop } from "./components/auth-shell";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return <AuthBackdrop>{children}</AuthBackdrop>;
}
