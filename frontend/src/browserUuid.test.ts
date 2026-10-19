import assert from "node:assert/strict";
import test from "node:test";
import { browserUuid } from "./browserUuid.ts";

test("uses native randomUUID when available", () => {
  const cryptoApi = { randomUUID: () => "native-id" } as unknown as Crypto;
  assert.equal(browserUuid(cryptoApi), "native-id");
});

test("creates a version 4 UUID on HTTP origins without randomUUID", () => {
  const cryptoApi = {
    getRandomValues: (bytes: Uint8Array) => {
      bytes.set(Array.from({ length: 16 }, (_, index) => index));
      return bytes;
    },
  } as unknown as Crypto;
  assert.equal(browserUuid(cryptoApi), "00010203-0405-4607-8809-0a0b0c0d0e0f");
});
