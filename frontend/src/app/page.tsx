"use client";

import { useEffect, useState } from "react";

export default function Home() {
  const [status, setStatus] = useState("checking...");

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`)
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus("unreachable"));
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <h1 className="text-xl">
        Backend status: <span className="font-mono">{status}</span>
      </h1>
    </main>
  );
}