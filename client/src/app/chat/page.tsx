'use client';
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { App, Button, Drawer, Grid, Menu, Popconfirm, Tooltip } from 'antd';
import { X, Plus, Menu as MenuIcon, MessageSquare, Trash2 } from 'lucide-react';
import MessageList, { type Message } from '@/src/components/MessageList';
import ChatInput from '@/src/components/ChatInput';
import { imageToBase64 } from '@/src/lib/image';

// --- Types ---

type ChatSession = {
    id: string;
    preview: string;
    timestamp: number;
};

type HistoryItem = {
    role: 'user' | 'assistant' | 'ta';
    content: string;
    sources?: Message['sources'];
};

// --- Helpers ---
const createNewSessionId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return `session-${crypto.randomUUID()}`;
    }
    return `session-${Date.now().toString(36)}`;
};

const createSession = (id: string): ChatSession => ({
    id,
    preview: "New Conversation",
    timestamp: Date.now(),
});

export default function ChatPage() {
    const { message } = App.useApp();
    // Phones get the history in a drawer over the chat; wider screens get a side panel
    const isMobile = Grid.useBreakpoint().md === false;

    // --- State ---
    const [messages, setMessages] = useState<Message[]>([]);
    const [sessionId, setSessionId] = useState('');
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    
    const [isLoading, setIsLoading] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);

    // Mirrors the active session so async responses can tell whether they are stale.
    const activeSessionRef = useRef('');
    
    const fetchChatHistory = async (id: string) => {
        setIsLoading(true);
        setMessages([]); // Clear previous messages while loading
        try {
            const res = await fetch(`/api/py/history/${id}`);
            if (!res.ok) throw new Error("Failed to load history");
            
            const data = await res.json();
            if (activeSessionRef.current !== id) return; // user switched sessions meanwhile
            
            if (data.history && data.history.length > 0) {
                const formattedMessages: Message[] = (data.history as HistoryItem[]).map((msg) => ({
                    role: msg.role === 'user' ? 'user' : 'ta',
                    content: msg.content,
                    sources: msg.sources || []
                }));
                setMessages(formattedMessages);
            } else {
                setMessages([{ role: 'ta', content: "Hello! I'm **Cerebrix**, your AI tutor for Probability. How can I help you today?" }]);
            }
        } catch (error) {
            console.error(error);
            if (activeSessionRef.current !== id) return;
            setMessages([{ role: 'ta', content: "Hello! I'm Cerebrix. (Could not load history, starting fresh)." }]);
        } finally {
            if (activeSessionRef.current === id) setIsLoading(false);
        }
    };

    // --- Initialization ---
    useEffect(() => {
        /* eslint-disable react-hooks/set-state-in-effect -- localStorage/sessionStorage only exist in the browser, so state is restored after mount */
        let parsedSessions: ChatSession[] = [];
        try {
            const savedSessionsRaw = localStorage.getItem('my_chat_sessions');
            const saved = savedSessionsRaw ? JSON.parse(savedSessionsRaw) : [];
            if (Array.isArray(saved)) parsedSessions = saved;
        } catch (err) {
            console.error("Ignoring corrupt saved sessions:", err);
        }
        setSessions(parsedSessions);

        let currentId = sessionStorage.getItem('chatSessionId');
        
        if (!currentId) {
            currentId = createNewSessionId();
            sessionStorage.setItem('chatSessionId', currentId);
            
            if (!parsedSessions.find(s => s.id === currentId)) {
                const newSession = createSession(currentId);
                parsedSessions = [newSession, ...parsedSessions];
                setSessions(parsedSessions);
                localStorage.setItem('my_chat_sessions', JSON.stringify(parsedSessions));
            }
        }
        
        if (window.innerWidth < 768) setIsSidebarOpen(false); // start with the chat visible on phones
        activeSessionRef.current = currentId;
        setSessionId(currentId);
        fetchChatHistory(currentId);
        /* eslint-enable react-hooks/set-state-in-effect */
    }, []);

    // --- Actions ---

    const handleNewChat = (existingSessions: ChatSession[] = sessions) => {
        const newId = createNewSessionId();
        const newSession = createSession(newId);
        
        const updatedSessions = [newSession, ...existingSessions];
        setSessions(updatedSessions);
        localStorage.setItem('my_chat_sessions', JSON.stringify(updatedSessions));
        
        sessionStorage.setItem('chatSessionId', newId);
        activeSessionRef.current = newId;
        setSessionId(newId);
        setIsLoading(false);
        setMessages([{ role: 'ta', content: "Hello! I'm **Cerebrix**. New session started. How can I help?" }]);
        
        if (window.innerWidth < 768) setIsSidebarOpen(false);
    };

    const handleSelectSession = (id: string) => {
        if (id === sessionId) return;
        sessionStorage.setItem('chatSessionId', id);
        activeSessionRef.current = id;
        setSessionId(id);
        fetchChatHistory(id);
        if (window.innerWidth < 768) setIsSidebarOpen(false);
    };

    const handleDeleteSession = async (idToDelete: string) => {
        // 1. Update Frontend State immediately
        const updatedSessions = sessions.filter(s => s.id !== idToDelete);
        setSessions(updatedSessions);
        localStorage.setItem('my_chat_sessions', JSON.stringify(updatedSessions));

        // 2. Handle active session logic
        if (idToDelete === sessionId) {
            if (updatedSessions.length > 0) {
                // Switch to the first available session
                handleSelectSession(updatedSessions[0].id);
            } else {
                // No sessions left, create a fresh one (from the filtered list, not stale state)
                handleNewChat(updatedSessions);
            }
        }

        // 3. Call Backend to delete from DB
        try {
            const res = await fetch(`/api/py/history/${idToDelete}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            message.success("Chat deleted.");
        } catch (err) {
            console.error("Failed to delete from backend:", err);
            message.error("The chat was removed here, but the server could not delete its history.");
        }
    };

    const updateSessionPreview = (id: string, text: string) => {
        const updated = sessions.map(s => 
            s.id === id ? { ...s, preview: text.substring(0, 30) + (text.length > 30 ? '...' : '') } : s
        );
        const current = updated.find(s => s.id === id);
        const others = updated.filter(s => s.id !== id);
        const finalSort = current ? [current, ...others] : others;
        
        setSessions(finalSort);
        localStorage.setItem('my_chat_sessions', JSON.stringify(finalSort));
    };

    const handleSend = async (userMsg: string, currentImage: File | null) => {
        const sendId = sessionId;
        setMessages(prev => [...prev, { role: 'user', content: userMsg || "[Image Uploaded]" }]);
        updateSessionPreview(sessionId, userMsg || "Image Query");

        setIsLoading(true);

        try {
            let imageData = null;
            if (currentImage) imageData = await imageToBase64(currentImage);

            const res = await fetch('/api/py/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: userMsg, session_id: sessionId, image_data: imageData })
            });

            const data = await res.json();
            if(!res.ok) throw new Error(data.detail || "Error");

            // The answer is saved server-side, so it shows up when the user returns to that chat.
            if (activeSessionRef.current !== sendId) return;
            setMessages(prev => [...prev, { role: 'ta', content: data.answer, sources: data.sources }]);
        } catch (error) {
            console.error(error);
            if (activeSessionRef.current !== sendId) return;
            message.error("The tutor could not answer. Is the backend running?");
            setMessages(prev => [...prev, { role: 'ta', content: "I'm having trouble connecting to my knowledge base. Please try again in a moment." }]);
        } finally {
            if (activeSessionRef.current === sendId) setIsLoading(false);
        }
    };

    const sidebar = (
        <div className="flex flex-col h-full">
            <div className="p-4 flex items-center gap-2">
                <Button type="primary" size="large" block icon={<Plus size={18} />} onClick={() => handleNewChat()}>
                    New chat
                </Button>
                {isMobile && (
                    <Button type="text" size="large" aria-label="Close history" icon={<X size={18} />} onClick={() => setIsSidebarOpen(false)} />
                )}
            </div>

            <div className="px-4 pb-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider">Recent chats</div>
            <div className="flex-1 overflow-y-auto px-2 scrollbar-thin">
                <Menu
                    mode="inline"
                    selectedKeys={[sessionId]}
                    onClick={({ key }) => handleSelectSession(key)}
                    className="border-e-0! bg-transparent!"
                    items={sessions.map((session) => ({
                        key: session.id,
                        icon: <MessageSquare size={16} />,
                        label: (
                            <div className="group flex items-center justify-between gap-2">
                                <span className="truncate">{session.preview}</span>
                                {/* Clicks inside the confirm popup must not also select the chat */}
                                <span onClick={(e) => e.stopPropagation()}>
                                    <Popconfirm
                                        title="Delete this chat?"
                                        description="Its history is removed from the server too."
                                        okText="Delete"
                                        okButtonProps={{ danger: true }}
                                        onConfirm={() => handleDeleteSession(session.id)}
                                    >
                                        <Button
                                            type="text"
                                            size="small"
                                            danger
                                            aria-label="Delete chat"
                                            className="opacity-60 md:opacity-0 group-hover:opacity-100 focus:opacity-100"
                                            icon={<Trash2 size={14} />}
                                        />
                                    </Popconfirm>
                                </span>
                            </div>
                        ),
                    }))}
                />
            </div>
        </div>
    );

    return (
        <div className="relative flex h-[calc(100vh-80px)] overflow-hidden">
            {isMobile ? (
                <Drawer
                    placement="left"
                    open={isSidebarOpen}
                    onClose={() => setIsSidebarOpen(false)}
                    size={280}
                    closable={false}
                    styles={{ body: { padding: 0 } }}
                >
                    {sidebar}
                </Drawer>
            ) : (
                <AnimatePresence mode='wait'>
                    {isSidebarOpen && (
                        <motion.aside
                            initial={{ width: 0, opacity: 0 }}
                            animate={{ width: 280, opacity: 1 }}
                            exit={{ width: 0, opacity: 0 }}
                            className="bg-black/20 border-r border-white/5 backdrop-blur-md h-full shrink-0 overflow-hidden"
                        >
                            {sidebar}
                        </motion.aside>
                    )}
                </AnimatePresence>
            )}

            {/* --- MAIN CHAT AREA --- */}
            <main className="flex-1 flex flex-col relative min-w-0">
                <div className="absolute top-4 left-4 z-10">
                    <Tooltip title={isSidebarOpen ? "Hide chats" : "Show chats"} placement="right">
                        <Button
                            aria-label={isSidebarOpen ? "Hide chats" : "Show chats"}
                            icon={isSidebarOpen && !isMobile ? <X size={18} /> : <MenuIcon size={18} />}
                            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                        />
                    </Tooltip>
                </div>

                <MessageList messages={messages} isLoading={isLoading} onExample={(q) => handleSend(q, null)} />

                <ChatInput isLoading={isLoading} onSend={handleSend} onBusyChange={setIsLoading} />
            </main>
        </div>
    );
}
