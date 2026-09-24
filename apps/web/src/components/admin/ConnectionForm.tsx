"use client";

import { useState } from "react";
import { Field, Input } from "@/components/ui/Input";
import { JsonField, Select } from "@/components/ui/JsonField";
import type { AgentConnectionOut } from "@/types/admin";

export const CONNECTION_TYPES = [
  { value: "openai_responses", label: "OpenAI GPT agent (Responses API)" },
  { value: "http", label: "Custom HTTP endpoint (JSON)" },
];

export interface ConnectionDraft {
  connection_type: string;
  api_endpoint: string;
  api_key: string;
  config: Record<string, unknown>;
}

export function emptyDraft(conn?: AgentConnectionOut | null): ConnectionDraft {
  const type = conn && conn.connection_type !== "origin" ? conn.connection_type : "openai_responses";
  return { connection_type: type, api_endpoint: conn?.api_endpoint ?? (type === "openai_responses" ? "https://api.openai.com/v1" : ""), api_key: "", config: conn?.config ?? {} };
}

function OptionInput({ draft, onChange, name, label, hint, placeholder }: { draft: ConnectionDraft; onChange: (d: ConnectionDraft) => void; name: string; label: string; hint?: string; placeholder?: string }) {
  const value = draft.config[name];
  return (
    <Field label={label} hint={hint}>
      <Input
        value={value == null ? "" : String(value)}
        placeholder={placeholder}
        onChange={(e) => {
          const config = { ...draft.config };
          if (e.target.value === "") delete config[name];
          else config[name] = name === "timeout_seconds" || name === "prompt_version" ? Number(e.target.value) || e.target.value : e.target.value;
          onChange({ ...draft, config });
        }}
      />
    </Field>
  );
}

/** Connection editor shared by the add-agent wizard and the agent detail page. The key is write-only. */
export function ConnectionForm({ draft, onChange, existing }: { draft: ConnectionDraft; onChange: (d: ConnectionDraft) => void; existing?: AgentConnectionOut | null }) {
  const [advanced, setAdvanced] = useState(false);
  const isOpenAI = draft.connection_type === "openai_responses";
  const looksLikeCurl = /^\s*curl\s/i.test(draft.api_key);
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Select
          label="How is this agent called?"
          value={draft.connection_type}
          onChange={(v) => onChange({ ...draft, connection_type: v, api_endpoint: v === "openai_responses" && !draft.api_endpoint ? "https://api.openai.com/v1" : draft.api_endpoint })}
          options={CONNECTION_TYPES}
        />
      </div>
      <div className="sm:col-span-2">
        <Field label="API endpoint" hint={isOpenAI ? "Base URL. The adapter calls POST {base}/responses with your prompt id below." : "Full URL. Origin sends POST {message, session_id, conversation_id, history, files} as JSON."}>
          <Input value={draft.api_endpoint} onChange={(e) => onChange({ ...draft, api_endpoint: e.target.value })} placeholder={isOpenAI ? "https://api.openai.com/v1" : "https://agent.example.com/chat"} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label="API key" hint={existing?.configured ? `Configured · ${existing.api_key_preview} — leave empty to keep it` : "Paste the key (or a cURL — only its Bearer token is kept). Stored encrypted; never shown again."}>
          <Input type="password" autoComplete="off" value={draft.api_key} onChange={(e) => onChange({ ...draft, api_key: e.target.value })} placeholder={existing?.configured ? "Enter a new key to rotate" : "sk-…"} />
        </Field>
        {looksLikeCurl ? <p className="mt-1 text-xs text-warning">That looks like a cURL command — only the Bearer token will be stored.</p> : null}
      </div>
      {isOpenAI ? (
        <>
          <OptionInput draft={draft} onChange={onChange} name="prompt_id" label="Prompt / agent id" hint="pmpt_… from the OpenAI dashboard (optional)" placeholder="pmpt_…" />
          <OptionInput draft={draft} onChange={onChange} name="model" label="Model" hint="Used when the prompt does not pin one" placeholder="gpt-4.1" />
        </>
      ) : (
        <>
          <OptionInput draft={draft} onChange={onChange} name="response_text_path" label="Reply text path" hint="JSON path of the reply text in the response" placeholder="reply" />
          <OptionInput draft={draft} onChange={onChange} name="session_id_path" label="Session id path" hint="JSON path of a session id to send back next turn (optional)" placeholder="session_id" />
          <OptionInput draft={draft} onChange={onChange} name="api_key_header" label="Auth header" hint="Default: Authorization: Bearer <key>" placeholder="X-API-Key" />
        </>
      )}
      <OptionInput draft={draft} onChange={onChange} name="timeout_seconds" label="Timeout (seconds)" placeholder="120" />
      <div className="sm:col-span-2">
        <button type="button" onClick={() => setAdvanced((v) => !v)} className="text-xs text-muted underline-offset-2 hover:underline">{advanced ? "Hide" : "Show"} raw options</button>
        {advanced ? <div className="mt-2"><JsonField label={isOpenAI ? "Options (model, prompt_id, prompt_version, store, timeout_seconds)" : "Options (api_key_header, body_template, response_text_path, session_id_path, files_path, timeout_seconds)"} value={draft.config} onChange={(config) => onChange({ ...draft, config })} rows={5} /></div> : null}
      </div>
    </div>
  );
}
