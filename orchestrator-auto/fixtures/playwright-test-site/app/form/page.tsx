"use client";

import Link from "next/link";

export default function FormPage() {
  return (
    <main style={{ padding: "2rem" }}>
      <h1>Form Page</h1>
      <form style={{ marginTop: "1rem" }}>
        <div>
          <label htmlFor="username">Username:</label>
          <br />
          <input
            type="text"
            id="username"
            name="username"
            data-testid="username"
            style={{ marginTop: "0.5rem", padding: "0.5rem" }}
          />
        </div>
      </form>
      <nav style={{ marginTop: "2rem" }}>
        <Link href="/">Back to home</Link>
      </nav>
    </main>
  );
}
