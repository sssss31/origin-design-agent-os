import { redirect } from "next/navigation";

export default async function ChatConversationRedirect({ params }: { params: Promise<{ conversationId: string }> }) {
  const { conversationId } = await params;
  redirect(`/c/${conversationId}`);
}
