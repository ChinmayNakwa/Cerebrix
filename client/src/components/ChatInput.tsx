'use client';
import { useState, useRef, useEffect } from 'react';
import { App, Button, Input, Tag, Tooltip, Upload } from 'antd';
import { Send, Mic, Image as ImageIcon, Square } from 'lucide-react';

type ChatInputProps = {
    isLoading: boolean;
    onSend: (text: string, image: File | null) => void;
    onBusyChange: (busy: boolean) => void;
};

export default function ChatInput({ isLoading, onSend, onBusyChange }: ChatInputProps) {
    const { message } = App.useApp();
    const [input, setInput] = useState('');
    const [isRecording, setIsRecording] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [selectedImage, setSelectedImage] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);

    // Thumbnail for the attached image, released when it changes
    useEffect(() => {
        if (!selectedImage) return;
        const url = URL.createObjectURL(selectedImage);
        setPreview(url); // eslint-disable-line react-hooks/set-state-in-effect -- object URLs only exist in the browser
        return () => URL.revokeObjectURL(url);
    }, [selectedImage]);

    const canSend = (input.trim() || selectedImage) && !isLoading;

    const handleSubmit = () => {
        if (!canSend) return;
        onSend(input.trim(), selectedImage);
        setInput('');
        setSelectedImage(null);
    };

    const transcribe = async (blob: Blob) => {
        const formData = new FormData();
        formData.append("audio_file", blob, "recording.webm");
        setIsTranscribing(true);
        onBusyChange(true);
        try {
            const res = await fetch('/api/py/transcribe', { method: 'POST', body: formData });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Transcription failed");
            if (typeof data.transcription === 'string') setInput(data.transcription);
        } catch (e) {
            console.error(e);
            message.error(e instanceof Error && e.message !== "Transcription failed"
                ? e.message
                : "Couldn't transcribe that recording. Please try again or type your question.");
        } finally {
            setIsTranscribing(false);
            onBusyChange(false);
        }
    };

    const toggleRecording = async () => {
        if (isRecording) {
            mediaRecorderRef.current?.stop();
            setIsRecording(false);
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            const chunks: BlobPart[] = [];
            recorder.ondataavailable = e => chunks.push(e.data);
            recorder.onstop = () => {
                stream.getTracks().forEach(track => track.stop());
                transcribe(new Blob(chunks, { type: 'audio/webm' }));
            };
            recorder.start();
            mediaRecorderRef.current = recorder;
            setIsRecording(true);
        } catch {
            message.error("Microphone access was denied.");
        }
    };

    return (
        <div className="p-4 md:p-6 z-20 relative">
            <div className="max-w-4xl mx-auto">
                {selectedImage && (
                    <Tag
                        closable
                        onClose={() => setSelectedImage(null)}
                        className="mb-2 flex! w-fit items-center gap-2 py-1!"
                        icon={preview
                            // eslint-disable-next-line @next/next/no-img-element -- a local object URL, not an optimizable asset
                            ? <img src={preview} alt="" className="h-8 w-8 rounded object-cover" />
                            : <ImageIcon size={14} />}
                    >
                        <span className="truncate max-w-[220px]">{selectedImage.name}</span>
                    </Tag>
                )}

                <div className="glass rounded-2xl p-2 flex items-end gap-1 shadow-2xl shadow-indigo-500/5 transition-all focus-within:border-indigo-500/50">
                    <Upload
                        accept="image/*"
                        showUploadList={false}
                        beforeUpload={(file) => { setSelectedImage(file); return false; }}
                    >
                        <Tooltip title="Attach a photo of your work">
                            <Button type="text" size="large" aria-label="Attach image" icon={<ImageIcon size={20} />} />
                        </Tooltip>
                    </Upload>

                    <Input.TextArea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
                        placeholder={isTranscribing ? "Transcribing..." : "Ask a question or describe a problem..."}
                        autoSize={{ minRows: 1, maxRows: 6 }}
                        variant="borderless"
                        // The bar around it shows focus (focus-within), so the field's own outline is dropped
                        className="text-base! outline-none!"
                    />

                    <Tooltip title={isRecording ? "Stop recording" : "Ask by voice"}>
                        <Button
                            type="text"
                            size="large"
                            danger={isRecording}
                            loading={isTranscribing}
                            aria-label={isRecording ? "Stop recording" : "Record a question"}
                            className={isRecording ? 'animate-pulse' : undefined}
                            icon={isRecording ? <Square size={18} /> : <Mic size={20} />}
                            onClick={toggleRecording}
                        />
                    </Tooltip>

                    <Button
                        type="primary"
                        size="large"
                        aria-label="Send"
                        disabled={!canSend}
                        icon={<Send size={18} />}
                        onClick={handleSubmit}
                    />
                </div>
                <div className="text-center mt-2 text-xs text-zinc-600">
                    Enter to send, Shift+Enter for a new line. Cerebrix can make mistakes, so check important results.
                </div>
            </div>
        </div>
    );
}
