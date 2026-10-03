'use client';
import { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { Send, Mic, Image as ImageIcon, StopCircle, X } from 'lucide-react';

type ChatInputProps = {
    isLoading: boolean;
    onSend: (text: string, image: File | null) => void;
    onBusyChange: (busy: boolean) => void;
};

export default function ChatInput({ isLoading, onSend, onBusyChange }: ChatInputProps) {
    const [input, setInput] = useState('');
    const [isRecording, setIsRecording] = useState(false);
    const [selectedImage, setSelectedImage] = useState<File | null>(null);

    const fileInputRef = useRef<HTMLInputElement>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);

    const handleSubmit = (e?: React.FormEvent) => {
        e?.preventDefault();
        if ((!input.trim() && !selectedImage) || isLoading) return;

        onSend(input, selectedImage);
        setInput('');
        setSelectedImage(null);
    };

    const toggleRecording = async () => {
        if (isRecording) {
            mediaRecorderRef.current?.stop();
            setIsRecording(false);
        } else {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const recorder = new MediaRecorder(stream);
                const chunks: BlobPart[] = [];
                recorder.ondataavailable = e => chunks.push(e.data);
                recorder.onstop = async () => {
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    const formData = new FormData();
                    formData.append("audio_file", blob, "recording.webm");
                    onBusyChange(true);
                    try {
                        const res = await fetch('/api/py/transcribe', { method: 'POST', body: formData });
                        const data = await res.json();
                        setInput(data.transcription);
                    } catch (e) { console.error(e); }
                    finally { onBusyChange(false); }
                    stream.getTracks().forEach(track => track.stop());
                };
                recorder.start();
                mediaRecorderRef.current = recorder;
                setIsRecording(true);
            } catch (err) { alert("Microphone access denied."); }
        }
    };

    return (
        <div className="p-4 md:p-6 z-20 relative">
            <div className="max-w-4xl mx-auto">
                {selectedImage && (
                    <motion.div initial={{opacity: 0, y: 10}} animate={{opacity: 1, y: 0}} className="absolute bottom-full left-4 md:left-6 mb-3 p-3 glass rounded-xl flex items-center gap-3">
                        <div className="w-8 h-8 bg-white/10 rounded flex items-center justify-center"><ImageIcon size={14}/></div>
                        <span className="text-xs text-zinc-300 truncate max-w-[200px]">{selectedImage.name}</span>
                        <button onClick={() => setSelectedImage(null)} className="hover:text-red-400"><X size={14}/></button>
                    </motion.div>
                )}

                <form onSubmit={handleSubmit} className="glass rounded-2xl p-2 flex items-center gap-2 shadow-2xl shadow-indigo-500/5 transition-all focus-within:border-indigo-500/50">
                    <button type="button" onClick={() => fileInputRef.current?.click()} className="p-3 hover:bg-white/10 rounded-xl text-zinc-400 hover:text-white transition">
                        <ImageIcon size={20} />
                    </button>
                    <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={(e) => { if(e.target.files?.[0]) setSelectedImage(e.target.files[0]); }} />

                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Ask a question..."
                        className="flex-grow bg-transparent border-none outline-none text-white placeholder-zinc-500 px-2 py-2"
                    />

                    <button type="button" onClick={toggleRecording} className={`p-3 rounded-xl transition ${isRecording ? 'text-red-500 animate-pulse bg-red-500/10' : 'text-zinc-400 hover:text-white hover:bg-white/10'}`}>
                        {isRecording ? <StopCircle size={20} /> : <Mic size={20} />}
                    </button>

                    <button type="submit" disabled={isLoading || (!input && !selectedImage)} className="bg-white text-black p-3 rounded-xl hover:scale-105 active:scale-95 transition disabled:opacity-50 disabled:scale-100">
                        <Send size={20} />
                    </button>
                </form>
                <div className="text-center mt-2 text-xs text-zinc-600">
                    Cerebrix can make mistakes. Check important info.
                </div>
            </div>
        </div>
    );
}
