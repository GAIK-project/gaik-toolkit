import { describe, expect, it } from "vitest";
import { menuPlacement } from "./menu-placement";

describe("menuPlacement", () => {
  it("opens under a field in the middle of the window, as on the start view", () => {
    expect(menuPlacement({ top: 380, bottom: 500 }, 170, 900)).toEqual({ below: true, maxHeight: null });
  });

  it("opens over a field at the bottom of the window, as in a chat", () => {
    expect(menuPlacement({ top: 760, bottom: 880 }, 170, 900)).toEqual({ below: false, maxHeight: null });
  });

  it("where neither side has room, takes the side with more and scrolls inside the window", () => {
    // 600 px tall: 100 px over the card, 180 - 8 = 172 under it, a 240 px menu.
    expect(menuPlacement({ top: 108, bottom: 420 }, 240, 600)).toEqual({ below: true, maxHeight: 164 });
    expect(menuPlacement({ top: 300, bottom: 560 }, 400, 600)).toEqual({ below: false, maxHeight: 284 });
  });
});
