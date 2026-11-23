import { describe, expect, it } from "vitest";
import {
  BPMN_SHOW_DATA_KEY,
  bpmnDataObjectsQuery,
  parseDataObjectsParam,
  readBpmnShowData,
  saveBpmnShowData,
} from "@/lib/bpmn-show-data";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

const blocked = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
};

describe("the Show data choice", () => {
  it("is kept under gaik.bpmn.showData", () => {
    expect(BPMN_SHOW_DATA_KEY).toBe("gaik.bpmn.showData");
  });

  it("shows the data when nothing is saved, when storage is blocked or missing, and for a value it does not know", () => {
    expect(readBpmnShowData(memoryStorage())).toBe(true);
    expect(readBpmnShowData(blocked)).toBe(true);
    expect(readBpmnShowData(null)).toBe(true);
    expect(readBpmnShowData(memoryStorage({ [BPMN_SHOW_DATA_KEY]: "maybe" }))).toBe(true);
  });

  it("reads back what was saved", () => {
    const storage = memoryStorage();
    saveBpmnShowData(false, storage);
    expect(storage.data.get(BPMN_SHOW_DATA_KEY)).toBe("0");
    expect(readBpmnShowData(storage)).toBe(false);
    saveBpmnShowData(true, storage);
    expect(storage.data.get(BPMN_SHOW_DATA_KEY)).toBe("1");
    expect(readBpmnShowData(storage)).toBe(true);
  });

  it("does not throw when storage is blocked", () => {
    expect(() => saveBpmnShowData(false, blocked)).not.toThrow();
    expect(() => saveBpmnShowData(false, null)).not.toThrow();
  });
});

describe("the data_objects parameter", () => {
  it("is only sent to leave the data out", () => {
    expect(bpmnDataObjectsQuery(true)).toBe("");
    expect(bpmnDataObjectsQuery(false)).toBe("?data_objects=0");
  });

  it("reads 0 and 1, defaults to the data, and refuses anything else", () => {
    expect(parseDataObjectsParam(null)).toBe(true);
    expect(parseDataObjectsParam("1")).toBe(true);
    expect(parseDataObjectsParam("0")).toBe(false);
    for (const value of ["", "2", "-1", "yes", "true", " 0"]) {
      expect(parseDataObjectsParam(value)).toBeNull();
    }
  });
});
