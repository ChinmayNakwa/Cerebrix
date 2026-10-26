import * as motion from 'framer-motion/client';
import Link from 'next/link';
import { Button, Card, Statistic } from 'antd';
import { ArrowRight, Video, BookOpen, Network, GraduationCap, AudioLines, MessageSquareText } from 'lucide-react';

// Corpus size as ingested (Postgres maths_ta_db)
const stats = [
  { title: "Lecture videos", value: 29 },
  { title: "Textbook pages", value: 242 },
  { title: "Searchable passages", value: 4993 },
  { title: "Linked concepts", value: 4323 },
];

const features = [
  {
    icon: <Video className="text-red-500" />,
    title: "Every Lecture, Searchable",
    desc: "Captions and the slides on screen from all 29 CS109 lectures. Answers link to the exact moment in the video."
  },
  {
    icon: <BookOpen className="text-blue-500" />,
    title: "Grounded in the Textbook",
    desc: "The course reader, formulas included, searched by meaning and by keyword, with page numbers on every source."
  },
  {
    icon: <Network className="text-amber-500" />,
    title: "Concept Graph",
    desc: "Definitions, theorems, formulas and examples linked across the book and lectures, so closely related material comes along."
  },
  {
    icon: <GraduationCap className="text-purple-500" />,
    title: "Two Ways to Teach",
    desc: "Ask what something is and get a direct answer. Share a problem or a photo of your work and get Socratic hints instead."
  },
  {
    icon: <AudioLines className="text-emerald-500" />,
    title: "Voice In, Voice Out",
    desc: "Ask by voice and have answers read aloud. Speech is transcribed and spoken by models running on the server."
  },
  {
    icon: <MessageSquareText className="text-sky-500" />,
    title: "Conversational Memory",
    desc: "Follow-ups build on earlier turns, and each chat is saved so you can pick it up later."
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-col items-center min-h-screen pt-20 px-4 relative overflow-hidden">

        {/* Hero Section */}
        <section className="text-center max-w-4xl mx-auto mt-16 mb-16 relative z-10">
            <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
                className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs font-medium text-indigo-300 mb-6"
            >
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                </span>
                Stanford CS109 · Probability for Computer Scientists
            </motion.div>

            <motion.h1
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-5xl md:text-7xl font-bold tracking-tight mb-6 leading-[1.1]"
            >
                Your AI Teaching Assistant for <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-400 to-indigo-400 animate-gradient">
                    Active Learning
                </span>
            </motion.h1>

            <motion.p
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="text-secondary text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed"
            >
                Cerebrix turns a full lecture series and its textbook into a tutor you can talk to.
                Ask about a concept for a clear answer, or share the problem you&apos;re stuck on and get hints that lead you to the solution.
            </motion.p>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="flex flex-col sm:flex-row gap-4 justify-center"
            >
                <Link href="/chat">
                    <Button size="large" shape="round" className="h-14! px-8! text-lg! font-bold! bg-white! text-black! border-0! hover:scale-105 transition-transform">
                        Start Tutoring <ArrowRight size={20} />
                    </Button>
                </Link>
                <Link href="/about">
                    <Button size="large" shape="round" ghost className="h-14! px-8! text-lg! font-bold! text-white! border-white/15!">
                        See How It Works
                    </Button>
                </Link>
            </motion.div>
        </section>

        {/* Corpus size */}
        <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-5xl w-full mb-16"
        >
            {stats.map((s) => (
                <Card key={s.title} size="small" className="glass! text-center">
                    <Statistic title={s.title} value={s.value} />
                </Card>
            ))}
        </motion.section>

        {/* Features Grid */}
        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl w-full mb-24">
            {features.map((f, i) => (
                <motion.div
                    key={f.title}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.08 }}
                    className="glass glass-hover p-6 rounded-2xl transition-all duration-300 group"
                >
                    <div className="bg-surface-highlight w-12 h-12 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                        {f.icon}
                    </div>
                    <h3 className="text-xl font-bold mb-2">{f.title}</h3>
                    <p className="text-secondary leading-relaxed">{f.desc}</p>
                </motion.div>
            ))}
        </section>
    </div>
  );
}
