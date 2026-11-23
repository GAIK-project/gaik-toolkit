// The login page shows only notices it knows by code. The query string carries
// the code, never the text, so a link cannot put words of its own on the page.

import {
  LOGIN_ERROR_CODES,
  LOGIN_MESSAGE_CODES,
  type Dict,
  type LoginErrorCode,
  type LoginMessageCode,
} from "@/lib/i18n";

export function loginError(t: Dict, code: string | undefined): string | null {
  return LOGIN_ERROR_CODES.includes(code as LoginErrorCode)
    ? t.loginErrors[code as LoginErrorCode]
    : null;
}

export function loginMessage(t: Dict, code: string | undefined): string | null {
  return LOGIN_MESSAGE_CODES.includes(code as LoginMessageCode)
    ? t.loginMessages[code as LoginMessageCode]
    : null;
}
