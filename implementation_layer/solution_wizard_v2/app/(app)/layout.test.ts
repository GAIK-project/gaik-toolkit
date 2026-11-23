import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  user: { email: "alice@example.test" } as { email: string } | null,
  sidebarCookie: undefined as string | undefined,
  listSessions: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "gaik_sidebar" && state.sidebarCookie ? { value: state.sidebarCookie } : undefined,
  }),
}));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`REDIRECT ${url}`);
  },
}));
vi.mock("@/app/login/actions", () => ({ signOut: vi.fn() }));
// The layout is read as the tree it returns; what it places in it is not rendered.
vi.mock("@/components/sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/components/locale-switcher", () => ({ LocaleSwitcher: () => null }));
vi.mock("@/components/icons", () => ({ Icon: () => null }));
vi.mock("@/lib/current-user", () => ({ getCurrentUser: async () => state.user }));
vi.mock("@/lib/sessions", () => ({ listSessions: state.listSessions }));
vi.mock("@/lib/logger", () => ({ logger: { error: vi.fn() } }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "fi", t: actual.dictionary("fi") }) };
});

import { Sidebar } from "@/components/sidebar";
import { logger } from "@/lib/logger";
import AppLayout from "./layout";

type Props = Record<string, unknown> & { children?: ReactNode };

/** Every element of the tree the layout returned, without rendering any. */
function elements(node: ReactNode, found: ReactElement<Props>[] = []): ReactElement<Props>[] {
  if (Array.isArray(node)) node.forEach((child) => elements(child, found));
  else if (isValidElement<Props>(node)) {
    found.push(node);
    elements(node.props.children, found);
  }
  return found;
}

async function shell() {
  const tree = elements(await AppLayout({ children: "the open page" }));
  const sidebar = tree.find((el) => el.type === Sidebar);
  const main = tree.find((el) => "data-shell-main" in el.props);
  return { sidebar: sidebar!.props, main: main!.props };
}

beforeEach(() => {
  vi.clearAllMocks();
  state.user = { email: "alice@example.test" };
  state.sidebarCookie = undefined;
  state.listSessions.mockResolvedValue([]);
});

describe("the signed-in shell", () => {
  it("lists the signed-in user's sessions beside the page", async () => {
    const { sidebar, main } = await shell();
    expect(state.listSessions).toHaveBeenCalledWith("alice@example.test");
    expect(sidebar).toMatchObject({ email: "alice@example.test", rows: [], loadFailed: false });
    expect(main.children).toBe("the open page");
  });

  it("a list that cannot be read leaves the open page standing, and the sidebar says so", async () => {
    state.listSessions.mockRejectedValue(new Error("wizard_api 503"));
    const { sidebar, main } = await shell();
    expect(sidebar).toMatchObject({ rows: [], loadFailed: true });
    expect(main.children).toBe("the open page");
    expect(logger.error).toHaveBeenCalledTimes(1);
  });

  it("renders the sidebar folded when the viewer left it so", async () => {
    expect((await shell()).sidebar.defaultCollapsed).toBe(false);
    state.sidebarCookie = "collapsed";
    expect((await shell()).sidebar.defaultCollapsed).toBe(true);
  });

  it("sends a visitor who is not signed in to the sign-in page, and lists nothing", async () => {
    state.user = null;
    await expect(AppLayout({ children: null })).rejects.toThrow("REDIRECT /login");
    expect(state.listSessions).not.toHaveBeenCalled();
  });
});
