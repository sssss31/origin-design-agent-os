"use client";

import { Check, Copy } from "lucide-react";
import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function CodeBlock({ children }: { children?: React.ReactNode }) {
  const ref = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(ref.current?.innerText ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className="group relative">
      <pre ref={ref}>{children}</pre>
      <button type="button" onClick={() => void copy()} className="absolute right-2 top-2 rounded-md border border-border bg-surface p-1 text-muted opacity-0 transition group-hover:opacity-100" aria-label="Copy code">
        {copied ? <Check size={13} /> : <Copy size={13} />}
      </button>
    </div>
  );
}

/** Chat-style markdown (GFM): the agent's text is rendered, never executed. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
