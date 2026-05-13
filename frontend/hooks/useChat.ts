"use client";

import { useState, useCallback } from "react";
import { api, ChatMessage, Citation } from "@/lib/api";

export interface MessageWithCitations extends ChatMessage {
  citations?: Citation[];
  isLoading?: boolean;
  error?: string;
}

export function useChat(merchantId?: string) {
  const [messages, setMessages] = useState<MessageWithCitations[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isLoading) return;

      const userMsg: MessageWithCitations = { role: "user", content: text };
      const placeholder: MessageWithCitations = {
        role: "assistant",
        content: "",
        isLoading: true,
      };

      setMessages((prev) => [...prev, userMsg, placeholder]);
      setIsLoading(true);

      // Build history (exclude the placeholder we just added)
      const history: ChatMessage[] = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        const data = await api.sendMessage(text, history, merchantId);
        setMessages((prev) => [
          ...prev.slice(0, -1),
          {
            role: "assistant",
            content: data.response,
            citations: data.citations,
          },
        ]);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Something went wrong";
        setMessages((prev) => [
          ...prev.slice(0, -1),
          {
            role: "assistant",
            content: "",
            error: message,
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [messages, isLoading, merchantId]
  );

  const clearHistory = useCallback(() => setMessages([]), []);

  return { messages, isLoading, sendMessage, clearHistory };
}
