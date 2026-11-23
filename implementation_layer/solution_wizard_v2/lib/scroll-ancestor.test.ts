import { describe, expect, it } from "vitest";
import { scrollClip, scrollTarget, type ScrollBox } from "./scroll-ancestor";

type Box = ScrollBox & { name: string; overflowY: string };

function box(name: string, overflowY: string, parent: Box | null, scroll: [top: number, content: number, shown: number]): Box {
  return { name, overflowY, parentElement: parent, scrollTop: scroll[0], scrollHeight: scroll[1], clientHeight: scroll[2] };
}
const overflowOf = (el: ScrollBox) => (el as Box).overflowY;

/** page > workspace (scrolls) > tab panel (scrolls) > form > list */
function layout(panel: [number, number, number], workspace: [number, number, number], pageScroll: [number, number, number]) {
  const page = box("page", "visible", null, pageScroll);
  const ws = box("workspace", "auto", page, workspace);
  const tab = box("panel", "auto", ws, panel);
  const form = box("form", "visible", tab, [0, 2000, 2000]);
  const list = box("list", "visible", form, [0, 900, 900]);
  return { page, ws, tab, list };
}

describe("scrollTarget", () => {
  it("is the nearest ancestor that scrolls and has room that way, whatever its class", () => {
    const { page, list } = layout([100, 2000, 500], [0, 600, 600], [0, 900, 900]);
    expect(scrollTarget(list, 1, page, overflowOf)?.name).toBe("panel");
    expect(scrollTarget(list, -1, page, overflowOf)?.name).toBe("panel");
  });

  it("skips an ancestor whose overflow does not scroll, however tall its content", () => {
    const page = box("page", "visible", null, [0, 900, 900]);
    const outer = box("outer", "scroll", page, [0, 3000, 500]);
    const hidden = box("hidden", "hidden", outer, [0, 5000, 100]);
    const list = box("list", "visible", hidden, [0, 900, 900]);
    expect(scrollTarget(list, 1, page, overflowOf)?.name).toBe("outer");
  });

  it("hands over to the container outside one that is at its end", () => {
    // The tab panel is at its bottom; the workspace around it can still go down.
    const { page, list } = layout([1500, 2000, 500], [0, 900, 600], [0, 900, 900]);
    expect(scrollTarget(list, 1, page, overflowOf)?.name).toBe("workspace");
    // Up, the panel has all its way to go.
    expect(scrollTarget(list, -1, page, overflowOf)?.name).toBe("panel");
  });

  it("falls back to the page when no container scrolls, and to nothing when the page is at its end", () => {
    // A layout where the tab panel fits its content and the page scrolls.
    const { page, list } = layout([0, 500, 500], [0, 600, 600], [200, 3000, 900]);
    expect(scrollTarget(list, 1, page, overflowOf)?.name).toBe("page");
    page.scrollTop = 2100;
    expect(scrollTarget(list, 1, page, overflowOf)).toBeNull();
    expect(scrollTarget(list, -1, page, overflowOf)?.name).toBe("page");
  });

  it("does not take a last fraction of a pixel for room", () => {
    const { page, list } = layout([1499.5, 2000, 500], [0, 600, 600], [0, 900, 900]);
    expect(scrollTarget(list, 1, page, overflowOf)).toBeNull();
  });
});

describe("scrollClip", () => {
  it("is the nearest ancestor that scrolls its content, with room or not", () => {
    const { list } = layout([0, 500, 500], [0, 900, 600], [0, 900, 900]);
    expect(scrollClip(list, overflowOf)?.name).toBe("panel");
  });

  it("is null when the window is the only view", () => {
    const page = box("page", "visible", null, [0, 3000, 900]);
    const list = box("list", "visible", page, [0, 900, 900]);
    expect(scrollClip(list, overflowOf)).toBeNull();
  });
});
