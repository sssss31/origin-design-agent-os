"use client";

export function TopBar({ title }: { title?: string }) {
  return (
    <header className="flex h-12 items-center border-b border-border bg-surface px-5">
      <h1 className="truncate text-sm font-semibold">{title ?? ""}</h1>
    </header>
  );
}
