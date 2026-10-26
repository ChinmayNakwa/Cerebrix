'use client';
import { useEffect, useRef, useState } from 'react';
import { App, Button, Tooltip } from 'antd';
import { Volume2, Square } from 'lucide-react';

const SYMBOL_WORDS: Record<string, string> = {
    sim: 'distributed as', le: 'is at most', leq: 'is at most', ge: 'is at least', geq: 'is at least',
    neq: 'is not equal to', approx: 'is approximately', cdot: 'times', times: 'times', infty: 'infinity',
    to: 'to', rightarrow: 'to', mid: 'given', sum: 'the sum of', prod: 'the product of', int: 'the integral of',
    sqrt: 'the square root of', ldots: '', dots: '', cdots: '', boxed: '',
};

// Rough spoken form of LaTeX: \frac{a}{b} -> "a over b", X\sim\text{Bern}(p) -> "X distributed as Bern (p)"
function speakTex(tex: string) {
    return tex
        .replace(/\\(?:text|mathrm|mathbb|mathcal|mathbf|mathit|operatorname|boxed)\{([^{}]*)\}/g, ' $1 ')
        .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, ' $1 over $2 ')
        .replace(/\\binom\{([^{}]*)\}\{([^{}]*)\}/g, ' $1 choose $2 ')
        .replace(/\^\{?2\}?/g, ' squared ')
        .replace(/\\(?:left|right|[,;!]|quad|qquad)/g, ' ')
        .replace(/\\([a-zA-Z]+)/g, (_, cmd: string) => ` ${SYMBOL_WORDS[cmd] ?? cmd} `)
        .replace(/[{}_]/g, ' ')
        .replace(/\^/g, ' to the ')
        .replace(/\s+/g, ' ')
        .trim();
}

// Markdown answer -> plain sentences for text-to-speech. Display formulas are read in their rough
// spoken form; code is skipped.
export function toSpeech(markdown: string) {
    return markdown
        .replace(/```[\s\S]*?```/g, ' ')
        .replace(/\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]/g, (_, a: string, b: string) => ` ${speakTex(a ?? b)}. `)
        .replace(/\$([^$\n]+)\$|\\\(([\s\S]+?)\\\)/g, (_, a: string, b: string) => speakTex(a ?? b))
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/^\s{0,3}(?:#{1,6}|>|[-*+]|\d+\.)\s+/gm, '')
        .replace(/[*_`#|]/g, '')
        // Spelled out so they don't end a sentence when the text is split
        .replace(/\bi\.e\.,?/gi, 'that is,').replace(/\be\.g\.,?/gi, 'for example,')
        .replace(/\s+/g, ' ')
        .trim();
}

// Pieces of about `size` characters ending at sentence boundaries; the first is kept short so audio starts sooner
function chunk(text: string, size = 260, firstSize = 120) {
    const sentences = text.match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g) ?? [text];
    const pieces: string[] = [];
    let current = '';
    for (const s of sentences) {
        const limit = pieces.length ? size : firstSize;
        if (current && (current + s).length > limit) { pieces.push(current.trim()); current = ''; }
        current += s;
    }
    if (current.trim()) pieces.push(current.trim());
    return pieces;
}

async function synthesize(text: string, signal: AbortSignal) {
    const form = new FormData();
    form.append('text', text);
    const res = await fetch('/api/py/speak', { method: 'POST', body: form, signal });
    if (!res.ok) throw new Error(`Speech failed (${res.status})`);
    return URL.createObjectURL(await res.blob());
}

export default function SpeakButton({ text }: { text: string }) {
    const { message } = App.useApp();
    const [state, setState] = useState<'idle' | 'loading' | 'playing'>('idle');
    const abortRef = useRef<AbortController | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    const stop = () => {
        abortRef.current?.abort();
        abortRef.current = null;
        audioRef.current?.pause();
        audioRef.current = null;
        setState('idle');
    };

    useEffect(() => stop, []); // stop playback when the message unmounts

    const play = async () => {
        const controller = new AbortController();
        abortRef.current = controller;
        setState('loading');
        const pieces = chunk(toSpeech(text));
        try {
            // Synthesise the next piece while the current one plays
            // (a prefetch cut short by Stop is never awaited, hence the empty catch)
            let next = synthesize(pieces[0], controller.signal);
            for (let i = 0; i < pieces.length; i++) {
                const url = await next;
                if (i + 1 < pieces.length) {
                    next = synthesize(pieces[i + 1], controller.signal);
                    next.catch(() => {});
                }
                if (controller.signal.aborted) return;
                const audio = new Audio(url);
                audioRef.current = audio;
                setState('playing');
                await new Promise<void>((resolve, reject) => {
                    audio.onended = () => resolve();
                    audio.onerror = () => reject(new Error('Playback failed'));
                    controller.signal.addEventListener('abort', () => resolve());
                    audio.play().catch(reject);
                });
                URL.revokeObjectURL(url);
                if (controller.signal.aborted) return;
            }
            setState('idle');
        } catch (e) {
            if (controller.signal.aborted) return;
            console.error(e);
            message.error("Couldn't read this answer aloud.");
            stop();
        }
    };

    const busy = state !== 'idle';
    return (
        <Tooltip title={busy ? 'Stop' : 'Read aloud'}>
            <Button
                type="text"
                size="small"
                aria-label={busy ? 'Stop reading' : 'Read aloud'}
                loading={state === 'loading'}
                icon={state === 'playing' ? <Square size={14} /> : <Volume2 size={15} />}
                onClick={busy ? stop : play}
            />
        </Tooltip>
    );
}
