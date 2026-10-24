import ChatSection from "./components/chat-section";

// The top bar is part of ChatSection: it shows the conversation's title and
// the New chat button, which both depend on the chat's state.
export default function Home() {
  return (
    <main className="flex h-dvh w-screen flex-col bg-ia-page">
      <ChatSection />
    </main>
  );
}
