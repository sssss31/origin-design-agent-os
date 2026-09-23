"use client";

import { useParams } from "next/navigation";
import { ChatApp } from "@/components/chatbot/ChatApp";

export default function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  return <ChatApp conversationId={conversationId} />;
}
