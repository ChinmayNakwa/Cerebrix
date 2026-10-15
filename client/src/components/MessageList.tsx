'use client';
import { memo, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Card, Spin, Tag, Tooltip } from 'antd';
import { Sparkles, PlayCircle, BookOpen, Lightbulb, PenLine, Film, Sigma } from 'lucide-react';
import MathRenderer from '@/src/components/MathRenderer';

export type Message = {
    role: 'user' | 'ta';
    content: string;
    sources?: Array<{ source_type?: string; location: string; title?: string | null; url?: string | null }>;
};

type MessageListProps = {
    messages: Message[];
    isLoading: boolean;
    onExample: (question: string) => void;
};

const examples = [
    { icon: <Lightbulb size={16} className="text-amber-400" />, label: "Concept", text: "What is a p-value?" },
    { icon: <Sigma size={16} className="text-indigo-400" />, label: "Theorem", text: "Explain the central limit theorem." },
    { icon: <PenLine size={16} className="text-emerald-400" />, label: "Problem", text: "How do I find P(X > 3) for X ~ Poisson(2)?" },
    { icon: <Film size={16} className="text-red-400" />, label: "Lecture", text: "What does Lecture 4 cover about Bayes' theorem?" },
];

const isWebUrl = (url?: string | null): url is string => !!url && /^https?:\/\//i.test(url);

function SourceTag({ src }: { src: NonNullable<Message['sources']>[number] }) {
    const isVideo = src.source_type === 'video';
    const tag = (
        <Tag
            icon={isVideo ? <PlayCircle size={12} /> : <BookOpen size={12} />}
            color={isVideo ? 'red' : 'blue'}
            variant="filled"
            className="inline-flex! items-center gap-1 m-0!"
        >
            {src.location}
        </Tag>
    );
    const linked = isWebUrl(src.url)
        ? <a href={src.url} target="_blank" rel="noopener noreferrer" aria-label={`${src.location} (opens YouTube)`}>{tag}</a>
        : tag;
    return src.title ? <Tooltip title={src.title}>{linked}</Tooltip> : linked;
}

function MessageList({ messages, isLoading, onExample }: MessageListProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const showExamples = messages.length <= 1 && !isLoading;

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
                            <div className="mt-4 pt-3 border-t border-white/5">
                                <div className="mb-2 text-[11px] uppercase tracking-wider text-zinc-500">Sources</div>
                                <div className="flex flex-wrap gap-2">
                                    {msg.sources.map((src, i) => <SourceTag key={i} src={src} />)}
                                </div>
                            </div>
                        )}
                    </div>
                </motion.div>
            ))}

            {showExamples && (
                <div className="max-w-3xl">
                    <div className="mb-3 text-xs uppercase tracking-wider text-zinc-500">Try asking</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {examples.map((ex) => (
                            <Card
                                key={ex.text}
                                size="small"
                                hoverable
                                role="button"
                                tabIndex={0}
                                onClick={() => onExample(ex.text)}
                                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onExample(ex.text); } }}
                                className="glass!"
                            >
                                <div className="flex items-center gap-2 mb-1 text-xs text-zinc-500">{ex.icon}{ex.label}</div>
                                <div className="text-sm text-zinc-200">{ex.text}</div>
                            </Card>
                        ))}
                    </div>
                </div>
            )}

            {isLoading && (
                <div data-loading="true" className="flex items-center gap-3 text-zinc-400 text-sm ml-2 glass px-4 py-2 rounded-full w-fit">
                    <Spin size="small" />
                    <span>Thinking: searching the book and lectures...</span>
                </div>
            )}
            <div ref={messagesEndRef} />
        </div>
    );
}

export default memo(MessageList);
