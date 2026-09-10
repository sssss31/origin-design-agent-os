"use client";

import { useState } from "react";
import { Textarea } from "@/components/ui/Input";

/** Textarea bound to a JSON object; keeps invalid text local and reports parse errors inline. */
export function JsonField({ label, value, onChange, rows = 6 }: { label: string; value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void; rows?: number }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-muted">{label}</span>
      <Textarea
        rows={rows}
        className="font-mono text-xs"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const parsed = JSON.parse(e.target.value) as unknown;
            if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
              setError(null);
              onChange(parsed as Record<string, unknown>);
            } else setError("must be a JSON object");
          } catch (err) {
            setError(err instanceof Error ? err.message : "invalid JSON");
          }
        }}
      />
      {error ? <span className="block text-xs text-danger">{error}</span> : null}
    </label>
  );
}

export function Select({ label, value, onChange, options, className = "" }: { label?: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string }) {
  const el = (
    <select className={`w-full rounded-md border border-border bg-surface px-2 py-2 text-sm ${className}`} value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  if (!label) return el;
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-muted">{label}</span>
      {el}
    </label>
  );
}
