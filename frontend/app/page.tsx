import Header from "@/app/components/header";
import ChatSection from "./components/chat-section";

export default function Home() {
  return (
    <main className="h-dvh w-screen flex flex-col bg-ia-bg text-ia-text">
      <Header />
      <div className="flex-1 flex flex-col overflow-hidden">
        <ChatSection />
      </div>
    </main>
  );
}
