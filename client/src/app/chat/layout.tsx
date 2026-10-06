import type { Metadata } from "next";

// The chat page is a client component, so its title has to come from a layout.
export const metadata: Metadata = { title: "Tutor" };

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return children;
}
