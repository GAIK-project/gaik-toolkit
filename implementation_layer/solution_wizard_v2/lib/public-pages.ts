/** Pages anyone can open. Everything else needs a signed-in, allowed user. */
export function isPublicPage(path: string): boolean {
  return path.startsWith("/login") || path === "/privacy";
}
