'use client';
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Plus, Menu, MessageSquare, Trash2 } from 'lucide-react';
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

    const handleDeleteSession = async (e: React.MouseEvent, idToDelete: string) => {
        e.stopPropagation(); // Prevent triggering handleSelectSession
        
        if (!confirm("Are you sure you want to delete this chat history?")) return;

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
            await fetch(`/api/py/history/${idToDelete}`, { method: 'DELETE' });
        } catch (err) {
            console.error("Failed to delete from backend:", err);
            // Optional: Show a toast notification here
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
            setMessages(prev => [...prev, { role: 'ta', content: "I'm having trouble connecting to my knowledge base." }]);
        } finally {
            if (activeSessionRef.current === sendId) setIsLoading(false);
        }
    };

    return (
        <div className="relative flex h-[calc(100vh-80px)] overflow-hidden">
            
            {/* Tap-outside backdrop, phones only (the sidebar overlays the chat there) */}
            {isSidebarOpen && (
                <div
                    className="md:hidden absolute inset-0 z-20 bg-black/60"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* --- LEFT SIDEBAR --- */}
            <AnimatePresence mode='wait'>
                {isSidebarOpen && (
                    <motion.aside 
                        initial={{ width: 0, opacity: 0 }} 
                        animate={{ width: 280, opacity: 1 }} 
                        exit={{ width: 0, opacity: 0 }}
                        className="bg-zinc-950 md:bg-black/20 border-r border-white/5 backdrop-blur-md flex flex-col h-full z-30 absolute inset-y-0 left-0 md:relative"
                    >
                        <div className="p-4 flex items-center gap-2">
                            <button 
                                onClick={() => handleNewChat()}
                                className="w-full flex items-center justify-center gap-2 bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/30 text-indigo-100 p-3 rounded-xl transition-all shadow-sm"
                            >
                                <Plus size={18} />
                                <span className="text-sm font-medium">New Chat</span>
                            </button>
                            <button
                                onClick={() => setIsSidebarOpen(false)}
                                aria-label="Close sidebar"
                                className="md:hidden p-3 rounded-xl text-zinc-400 hover:text-white hover:bg-white/10 transition"
                            >
                                <X size={18} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto px-2 space-y-1 scrollbar-thin scrollbar-thumb-white/10">
                            <div className="px-2 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider">Recent History</div>
                            {sessions.map((session) => (
                                <div
                                    key={session.id}
                                    onClick={() => handleSelectSession(session.id)}
                                    className={`group relative w-full text-left p-3 rounded-lg text-sm transition-colors flex items-center gap-3 cursor-pointer ${
                                        sessionId === session.id 
                                        ? 'bg-white/10 text-white shadow-inner' 
                                        : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200'
                                    }`}
                                >
                                    <MessageSquare size={16} className="shrink-0" />
                                    <div className="truncate w-full pr-6">
                                        {session.preview}
                                    </div>

                                    {/* Delete Button (Visible on Hover) */}
                                    <button 
                                        onClick={(e) => handleDeleteSession(e, session.id)}
                                        className="absolute right-2 p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-400/10 rounded-md opacity-0 group-hover:opacity-100 transition-opacity"
                                        title="Delete chat"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </motion.aside>
                )}
            </AnimatePresence>

            {/* --- MAIN CHAT AREA --- */}
            <main className="flex-1 flex flex-col relative min-w-0">
                
                {/* Mobile/Sidebar Toggle Header */}
                <div className={`absolute top-4 left-4 z-10 ${isSidebarOpen ? 'max-md:hidden' : ''}`}>
                     <button 
                        onClick={() => setIsSidebarOpen(!isSidebarOpen)} 
                        aria-label={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
                        className="p-2 bg-black/40 backdrop-blur-sm border border-white/10 rounded-lg text-zinc-400 hover:text-white transition"
                    >
                        {isSidebarOpen ? <X size={18} /> : <Menu size={18} />}
                    </button>
                </div>

                <MessageList messages={messages} isLoading={isLoading} />

                <ChatInput isLoading={isLoading} onSend={handleSend} onBusyChange={setIsLoading} />
            </main>
        </div>
    );
}