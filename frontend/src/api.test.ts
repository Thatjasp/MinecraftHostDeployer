import { describe, expect, it } from "vitest";

import { errorMessage } from "./api";

describe("errorMessage", () => {
  it("uses a string detail as-is", () => {
    expect(errorMessage(401, { detail: "Invalid username or password" })).toBe(
      "Invalid username or password",
    );
  });

  it("joins validation errors with their field names", () => {
    const body = {
      detail: [
        { loc: ["body", "username"], msg: "String should match pattern" },
        { loc: ["body", "password"], msg: "String should have at least 8 characters" },
      ],
    };
    expect(errorMessage(422, body)).toBe(
      "username: String should match pattern; password: String should have at least 8 characters",
    );
  });

  it("falls back to the status code", () => {
    expect(errorMessage(500, null)).toBe("Request failed (500)");
  });
});
