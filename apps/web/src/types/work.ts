export interface WorkAgent {
  id: string;
  name: string;
  command: string;
  messages: number;
  last_used: string | null;
}

export interface WorkItem {
  conversation_id: string;
  title: string;
  project_id: string;
  project_name: string;
  status: "active" | "archived";
  created_at: string;
  last_message_at: string | null;
  agents_used: WorkAgent[];
  primary_agent: string | null;
  messages: number;
  files: number;
  outputs: number;
}
