"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function Home() {
  useEffect(() => {
    // Emit console messages for MCP testing
    console.warn("[mcp-test] warn from home");
    console.error("[mcp-test] error from home");

    // Trigger network requests for MCP testing
    fetch("/api/ping").catch(() => {});
    fetch("/api/fail").catch(() => {});
  }, []);

  return (
    <main style={{ padding: "2rem" }}>
      <h1>MCP Playwright Test Site</h1>
      <p>This site is for testing Playwright MCP tool passing.</p>
      <nav style={{ marginTop: "1rem" }}>
        <Link href="/form" data-testid="nav-form">
          Go to form
        </Link>
      </nav>
    </main>
  );
}
