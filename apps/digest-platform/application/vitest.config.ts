import { defineConfig } from "vitest/config";

// TypeScript 側のテストは tests/batch/ に置く。tests/runner/・tests/perf/ は Python の unittest なので対象にしない
export default defineConfig({
  test: {
    include: ["tests/batch/**/*.test.ts"],
  },
});
