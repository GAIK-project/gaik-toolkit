import { expect, test } from "bun:test";
import { clientIp } from "./client-ip";

test("the last x-forwarded-for entry is the address the router added", () => {
  expect(clientIp(new Headers({ "x-forwarded-for": "203.0.113.7" }))).toBe(
    "203.0.113.7",
  );
  expect(
    clientIp(new Headers({ "x-forwarded-for": " 1.2.3.4 , 203.0.113.7 " })),
  ).toBe("203.0.113.7");
});

test("a changed first entry keeps the same key", () => {
  const a = clientIp(
    new Headers({ "x-forwarded-for": "10.0.0.1, 203.0.113.7" }),
  );
  const b = clientIp(
    new Headers({ "x-forwarded-for": "10.0.0.2, 203.0.113.7" }),
  );
  expect(a).toBe(b);
});

test("without x-forwarded-for: x-real-ip, else anonymous", () => {
  expect(clientIp(new Headers({ "x-real-ip": "9.9.9.9" }))).toBe("9.9.9.9");
  expect(clientIp(new Headers({ "x-forwarded-for": " " }))).toBe("anonymous");
  expect(clientIp(new Headers())).toBe("anonymous");
});
