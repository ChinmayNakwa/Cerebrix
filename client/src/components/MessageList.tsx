'use client';
import { memo, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import MathRenderer from '@/src/components/MathRenderer';

export type Message = {
    role: 'user' | 'ta';
    content: string;
    sources?: Array<{ location: string; url: string }>;
};

type MessageListProps = {
    messages: Message[];
    isLoading: boolean;
};

function MessageList({ messages, isLoading }: MessageListProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    return (
        <div className="flex-grow overflow-y-auto p-4 md:p-6 space-y-6 pt-14 md:pt-6">
            {messages.map((msg, idx) => (
                <motion.div key={idx} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                    <div className={`max-w-[90%] md:max-w-[75%] p-5 rounded-3xl backdrop-blur-sm shadow-sm ${
                        msg.role === 'user'
                        ? 'bg-indigo-600/20 border border-indigo-500/30 text-white rounded-br-sm'
                        : 'glass text-zinc-100 rounded-bl-sm'
                    }`}>
                        <div className="flex items-center gap-2 mb-2 opacity-50 text-xs font-bold uppercase tracking-wider">
                            {msg.role === 'user' ? 'You' : <><Sparkles size={12} /> Cerebrix</>}
                        </div>
                        <MathRenderer content={msg.content} />

                        {msg.sources && msg.sources.length > 0 && (
                            <div className="mt-4 pt-3 border-t border-white/5 flex flex-wrap gap-2">
                                {msg.sources.map((src, i) => (
                                    <div key={i} className="text-[10px] uppercase tracking-wide bg-black/40 px-3 py-1.5 rounded-full border border-white/10 text-zinc-400">
                                        {src.location}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </motion.div>
            ))}
            {isLoading && (
                <div className="flex items-center gap-2 text-zinc-500 text-sm ml-4 bg-surface/50 px-4 py-2 rounded-full w-fit">
                    <Sparkles size={14} className="animate-pulse text-indigo-400"/>
                    <span>Thinking...</span>
                </div>
            )}
            <div ref={messagesEndRef} />
        </div>
    );
}

export default memo(MessageList);
