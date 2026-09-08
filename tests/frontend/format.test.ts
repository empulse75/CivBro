import { describe, it, expect } from "vitest";
import { fmtCount, fmtSize, fmtSpeed, fmtEta, fmtAgo } from "@lib/format";

describe("fmtCount", () => {
  it("handles millions", () => expect(fmtCount(1_500_000)).toBe("1.5M"));
  it("handles thousands", () => expect(fmtCount(1_500)).toBe("1.5k"));
  it("handles small numbers", () => expect(fmtCount(42)).toBe("42"));
  it("handles zero", () => expect(fmtCount(0)).toBe("0"));
});

describe("fmtSize", () => {
  it("handles GB", () => expect(fmtSize(2_000_000_000)).toBe("2.00 GB"));
  it("handles MB", () => expect(fmtSize(2_000_000)).toBe("2.0 MB"));
  it("handles KB", () => expect(fmtSize(2_000)).toBe("2 KB"));
  it("handles bytes", () => expect(fmtSize(500)).toBe("500 B"));
  it("handles zero", () => expect(fmtSize(0)).toBe("0"));
});

describe("fmtSpeed", () => {
  it("renders speed strings", () => expect(fmtSpeed(5_000_000)).toBe("5.0 MB/s"));
  it("returns empty for zero", () => expect(fmtSpeed(0)).toBe(""));
});

describe("fmtEta", () => {
  it("renders hours", () => expect(fmtEta(7200)).toBe("2h 0m"));
  it("renders minutes", () => expect(fmtEta(90)).toBe("1m 30s"));
  it("renders seconds", () => expect(fmtEta(45)).toBe("45s"));
  it("empty for zero", () => expect(fmtEta(0)).toBe(""));
});

describe("fmtAgo", () => {
  it("returns empty for null", () => expect(fmtAgo(null)).toBe(""));
  it("handles just-now", () => expect(fmtAgo(new Date().toISOString())).toBe("just now"));
  it("handles days ago", () => {
    const d = new Date(Date.now() - 3 * 86400 * 1000);
    expect(fmtAgo(d.toISOString())).toContain("d ago");
  });
});
