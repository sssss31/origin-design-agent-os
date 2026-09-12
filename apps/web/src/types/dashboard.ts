import type { ArtifactOut, AssetOut, ConversationOut } from "@/types/chat";

export interface RecentConversation extends ConversationOut {
  project_name: string;
  workspace_name: string;
  workspace_id: string;
  last_message_preview: string | null;
}

export interface LibraryOut {
  artifacts: ArtifactOut[];
  assets: AssetOut[];
  projects: { id: string; name: string; workspace_id: string; workspace_name: string }[];
}

export interface GraphNode {
  id: string;
  name: string;
  slug: string;
  command: string;
  description: string;
  is_manager: boolean;
  status: string;
  version: number | null;
  model: string | null;
  tools: string[];
  skills_count: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  routing_hint: string;
  is_failure_route: boolean;
}

export interface AgentGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface QuickStartOut {
  conversation_id: string;
  project_id: string;
  run: { run_id: string; status: string; event_stream_url: string; message_id: string | null };
}

export interface ProfileOut {
  display_name: string;
  email: string;
  role: "admin" | "member" | "viewer" | null;
  organization_name: string | null;
  counts: { projects: number; conversations: number; artifacts: number };
  joined_at: string;
}

export interface RecentRun {
  id: string;
  status: string;
  command: string | null;
  user_input: string;
  conversation_id: string;
  conversation_title: string;
  project_id: string;
  project_name: string;
  created_at: string;
  finished_at: string | null;
  node_statuses: Record<string, string>;
  agent_slugs: string[];
}
