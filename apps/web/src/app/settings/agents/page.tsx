import { redirect } from "next/navigation";

export default function SettingsAgentsRedirect() {
  redirect("/admin/agents");
}
