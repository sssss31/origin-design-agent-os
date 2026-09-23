"use client";

import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/Input";

/** Header / query key-value editor. Values may reference secrets as {{secrets.name}}. */
export function KeyValueEditor({ value, onChange, keyPlaceholder = "Header", valuePlaceholder = "Value or {{secrets.api_key}}" }: { value: Record<string, string>; onChange: (v: Record<string, string>) => void; keyPlaceholder?: string; valuePlaceholder?: string }) {
  const rows = Object.entries(value);
  const update = (i: number, k: string, v: string) => {
    const next = rows.map((r, j) => (j === i ? [k, v] : r));
    onChange(Object.fromEntries(next.filter(([key]) => key !== "" || true)));
  };
  return (
    <div className="space-y-1">
      {rows.map(([k, v], i) => (
        <div key={i} className="flex gap-1">
          <Input className="w-1/3 font-mono text-xs" placeholder={keyPlaceholder} value={k} onChange={(e) => update(i, e.target.value, v)} />
          <Input className="flex-1 font-mono text-xs" placeholder={valuePlaceholder} value={v} onChange={(e) => update(i, k, e.target.value)} />
          <button type="button" aria-label="Remove" className="px-1 text-faint hover:text-danger" onClick={() => onChange(Object.fromEntries(rows.filter((_, j) => j !== i)))}><Trash2 size={14} /></button>
        </div>
      ))}
      <button type="button" className="flex items-center gap-1 text-xs text-accent" onClick={() => onChange({ ...value, [`Header-${rows.length + 1}`]: "" })}><Plus size={12} /> Add row</button>
    </div>
  );
}
