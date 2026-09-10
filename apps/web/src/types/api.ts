/** Types mirroring apps/api/app/schemas. Keep in sync when the API changes. */

export type Role = "admin" | "member" | "viewer";

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown; request_id?: string | null };
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface UserOut {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
}

export interface MembershipOut {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  role: Role;
}

export interface MeResponse {
  user: UserOut;
  memberships: MembershipOut[];
  active_organization_id: string | null;
  capabilities: { admin_console: boolean } & Record<string, boolean>;
}

export interface WorkspaceOut {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: "active" | "archived";
  brand_config: Record<string, unknown>;
  rules_text: string | null;
  created_at: string;
  updated_at: string;
  my_role: Role;
}

export interface WorkspaceCreate {
  organization_id?: string;
  name: string;
  slug?: string;
  description?: string;
  rules_text?: string;
}

export interface WorkspaceMemberOut {
  user_id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface ProjectOut {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: "active" | "archived";
  summary_text: string | null;
  settings_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  my_role: Role;
}

export interface ProjectRuleOut {
  id: string;
  project_id: string;
  name: string;
  rule_text: string;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
