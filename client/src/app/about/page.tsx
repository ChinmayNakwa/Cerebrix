import type { Metadata } from 'next';
import * as motion from 'framer-motion/client';
import { Card, Statistic, Tabs, Tag } from 'antd';
import FlowDiagram from '@/src/components/FlowDiagram';
import { ingestionFlow, questionFlow } from '@/src/lib/architecture';

export const metadata: Metadata = { title: 'Architecture' };

const stack = [
    { name: "Next.js 16 + Ant Design 6", desc: "Chat interface", group: "Frontend" },
    { name: "FastAPI", desc: "API for questions, history and speech", group: "Backend" },
    { name: "LangGraph", desc: "The tutor's workflow, with chat history checkpointed in Postgres", group: "Backend" },
    { name: "gpt-oss:120b", desc: "Routing, answers, critique, reflection and concept extraction", group: "Ollama Cloud" },
    { name: "gemma4:31b", desc: "Reads photos of work, slides and hard textbook pages", group: "Ollama Cloud" },
    { name: "PostgreSQL 16 + pgvector", desc: "Passages, vectors, full-text index, concept graph and chats", group: "Data" },
    { name: "bge-base-en-v1.5", desc: "768-dimension embeddings for passages and questions", group: "Local model" },
    { name: "faster-whisper", desc: "Speech to text for voice questions", group: "Local model" },
    { name: "Kokoro-82M", desc: "Text to speech for read-aloud", group: "Local model" },
    { name: "Docling + PyMuPDF", desc: "Textbook parsing and page rendering", group: "Ingestion" },
    { name: "ffmpeg + yt-dlp", desc: "Lecture keyframes and playlist metadata", group: "Ingestion" },
    { name: "Cloudinary", desc: "Hosting for the extracted slide images", group: "Data" },
];

const groupColor: Record<string, string> = {
    Frontend: 'blue', Backend: 'geekblue', 'Ollama Cloud': 'purple', Data: 'cyan', 'Local model': 'green', Ingestion: 'gold',
};

// From backend/core/rag/evaluate.py on the 46-question golden set
const retrieval = [
    { title: "Right source ranked first", value: 76, suffix: "%" },
    { title: "Right source in the top 5", value: 98, suffix: "%" },
    { title: "Mean reciprocal rank", value: 0.842, precision: 3 },
    { title: "Search time", value: 50, prefix: "~", suffix: " ms" },
];

export default function AboutPage() {
  return (
    <div className="min-h-screen pt-24 pb-24 px-4 md:px-6 max-w-6xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-4xl md:text-5xl font-bold mb-6">Inside <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">Cerebrix</span></h1>

        <div className="glass p-6 md:p-8 rounded-3xl mb-12 space-y-4 text-lg text-secondary leading-relaxed">
          <p>
            While studying Stanford&apos;s CS109 on YouTube, I encountered a common frustration:
            there was no way to discuss problems or get guidance when attempting exercises.
            <strong> Cerebrix</strong> emerged from that need.
          </p>
          <p>
            It reads the whole course ahead of time (the textbook and every lecture) into a searchable knowledge base
            with a graph of how the ideas connect. When you ask something, a small agent decides how to help: a direct
            answer for a concept, or hints that lead you through a problem.
          </p>
        </div>

        <h2 className="text-2xl md:text-3xl font-bold text-white mb-2">How it works</h2>
        <p className="text-zinc-400 mb-4">Both pipelines as they run in the code. Click any step for details.</p>
        <Tabs
          size="large"
          className="mb-16"
          items={[
            {
              key: 'question',
              label: 'Answering a question',
              children: <FlowDiagram steps={questionFlow.steps} links={questionFlow.links} height={720} />,
            },
            {
              key: 'ingestion',
              label: 'Building the knowledge base',
              children: <FlowDiagram steps={ingestionFlow.steps} links={ingestionFlow.links} height={720} />,
            },
          ]}
        />

        <h2 className="text-2xl md:text-3xl font-bold text-white mb-2">Retrieval quality</h2>
        <p className="text-zinc-400 mb-4">
          Measured on 46 hand-checked questions about the book and lectures. Following the concept graph adds sections
          that are relevant 47% of the time, against 34% for simply taking more search results. A cross-encoder
          re-ranker was tried and left off because it made the first result worse.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-16">
          {retrieval.map((r) => (
            <Card key={r.title} size="small" className="glass!">
              <Statistic title={r.title} value={r.value} precision={r.precision} prefix={r.prefix} suffix={r.suffix} />
            </Card>
          ))}
        </div>

        <h2 className="text-2xl md:text-3xl font-bold text-white mb-4">Tech stack</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {stack.map((tech) => (
            <Card key={tech.name} size="small" className="glass!">
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className="font-semibold text-zinc-100">{tech.name}</span>
                <Tag color={groupColor[tech.group]} className="m-0! shrink-0">{tech.group}</Tag>
              </div>
              <div className="text-sm text-zinc-400">{tech.desc}</div>
            </Card>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
