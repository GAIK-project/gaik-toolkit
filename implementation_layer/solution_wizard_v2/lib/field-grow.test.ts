import { describe, expect, it } from "vitest";
import { fitField } from "./field-grow";

/** A field that records every height it is given, as a browser would see them. */
function field(offsetHeight: number, contentHeight: number) {
  const heights: string[] = [];
  let height = `${offsetHeight}px`;
  const el = {
    get offsetHeight() {
      return height === "auto" ? contentHeight + 2 : parseFloat(height);
    },
    get scrollHeight() {
      return height === "auto" ? contentHeight : Math.max(contentHeight, parseFloat(height) - 2);
    },
    style: {
      get height() {
        return height;
      },
      set height(value: string) {
        height = value;
        heights.push(value);
      },
      overflowY: "",
    },
  };
  return { el, heights };
}

const borders = () => 2;

describe("fitField", () => {
  it("grows from the height the field had, not from the measuring height", () => {
    const { el, heights } = field(34, 52);
    fitField(el, 160, borders);
    expect(heights).toEqual(["auto", "34px", "54px"]);
  });

  it("shrinks the same way when the text is sent", () => {
    const { el, heights } = field(74, 32);
    fitField(el, 160, borders);
    expect(heights).toEqual(["auto", "74px", "34px"]);
  });

  it("sets the height once when nothing changes or the field is not laid out", () => {
    const same = field(34, 32);
    fitField(same.el, 160, borders);
    expect(same.heights).toEqual(["auto", "34px"]);

    const hidden = field(0, 32);
    fitField(hidden.el, 160, borders);
    expect(hidden.heights).toEqual(["auto", "34px"]);
  });

  it("stops at the cap and scrolls only there", () => {
    const long = field(120, 400);
    fitField(long.el, 160, borders);
    expect(long.heights.at(-1)).toBe("160px");
    expect(long.el.style.overflowY).toBe("");

    const short = field(34, 52);
    fitField(short.el, 160, borders);
    expect(short.el.style.overflowY).toBe("hidden");
  });
});
