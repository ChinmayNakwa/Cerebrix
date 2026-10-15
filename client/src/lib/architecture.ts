// Data for the two diagrams on the Architecture page. It mirrors the backend: the LangGraph agent in
// backend/core/rag/agent.py and the ingestion stages in backend/ingestion/. Counts are from the ingested database.

export type StepKind = 'input' | 'llm' | 'local' | 'store' | 'decision' | 'output';

export type FlowStep = {
    id: string;
    label: string;
    sub: string;
    kind: StepKind;
    x: number;
    y: number;
    detail: string;
    tech: string[];
};

export type FlowLink = {
    from: string;
    to: string;
    label?: string;
    dashed?: boolean;
    // Handle ids on the step box: t/b = top in/bottom out, l/rt = left/right in, ls/r = left/right out
    fromSide?: 'b' | 'ls' | 'r';
    toSide?: 't' | 'l' | 'rt';
};

export const kindStyle: Record<StepKind, { name: string; color: string }> = {
    input: { name: 'Input', color: '#a1a1aa' },
    decision: { name: 'Decision', color: '#f59e0b' },
    llm: { name: 'LLM call (Ollama Cloud)', color: '#a78bfa' },
    local: { name: 'Runs locally', color: '#34d399' },
    store: { name: 'Storage', color: '#60a5fa' },
    output: { name: 'Output', color: '#f472b6' },
};

export const questionFlow: { steps: FlowStep[]; links: FlowLink[] } = {
    steps: [
        {
            id: 'message', label: 'Student message', sub: 'text, photo or voice', kind: 'input', x: 280, y: 0,
            detail: 'A question typed in the chat, optionally with a photo of handwritten work. Voice questions are transcribed first by faster-whisper on the server, then sent like typed text. The browser posts it to /ask with the chat\'s session id.',
            tech: ['Next.js', 'FastAPI /ask', 'faster-whisper small.en'],
        },
        {
            id: 'filters', label: 'Extract filters', sub: '"Lecture 4", "page 61"', kind: 'llm', x: 280, y: 100,
            detail: 'Pulls explicit pointers out of the question, such as a lecture number or a book page, so the search can be limited to that lecture or page range.',
            tech: ['gpt-oss:120b', 'structured output'],
        },
        {
            id: 'route', label: 'Route the question', sub: 'concept, problem or unclear', kind: 'decision', x: 280, y: 200,
            detail: 'Decides how to handle the message. Questions about what something is go to a direct answer; a problem to solve or a photo of work goes to the Socratic path; a message that cannot be acted on gets a clarifying question. Follow-ups are routed with the conversation history in view.',
            tech: ['gpt-oss:120b', 'LangGraph conditional edge'],
        },
        {
            id: 'search', label: 'Hybrid search', sub: 'top 5 sections + graph', kind: 'local', x: 0, y: 320,
            detail: 'Embeds the question with bge-base-en-v1.5 and searches the 4,993 passages two ways at once: vector similarity in pgvector and keyword full-text search, merged with reciprocal rank fusion. Each hit is widened to its section. Up to 2 more sections are added by following strong links in the concept graph from the top hits.',
            tech: ['bge-base-en-v1.5', 'pgvector', 'Postgres full text', 'RRF k=60', 'concept graph'],
        },
        {
            id: 'direct', label: 'Direct answer', sub: 'grounded in the sources', kind: 'llm', x: 0, y: 430,
            detail: 'Writes a clear answer from the retrieved book and lecture sections, with formulas in LaTeX. Definitions and concept questions are answered directly, without turning them into a guiding question.',
            tech: ['gpt-oss:120b'],
        },
        {
            id: 'image', label: 'Read the work', sub: 'if a photo is attached', kind: 'llm', x: 280, y: 320,
            detail: 'Transcribes the student\'s handwritten or screenshotted working from the photo, so the next step can check it line by line.',
            tech: ['gemma4:31b (vision)'],
        },
        {
            id: 'critique', label: 'Critique the work', sub: 'find the misstep, look up context', kind: 'llm', x: 280, y: 430,
            detail: 'Analyses the approach, identifies the concept the student may be missing, and decides whether a lookup in the book or lectures would help. If it would, a focused search (top 3 sections) runs before the hint is written.',
            tech: ['gpt-oss:120b', 'hybrid search (k=3)'],
        },
        {
            id: 'socratic', label: 'Socratic hint', sub: 'guide, don\'t solve', kind: 'llm', x: 280, y: 540,
            detail: 'Writes step-by-step guidance that points at the mistake and asks the student to take the next step themselves, using the critique and any retrieved context.',
            tech: ['gpt-oss:120b'],
        },
        {
            id: 'clarify', label: 'Clarifying question', sub: 'for unclear messages', kind: 'output', x: 560, y: 320,
            detail: 'For messages like "help" or "this one?", the router\'s short question back to the student. It skips the reflection check and goes straight into the chat history.',
            tech: ['LangGraph'],
        },
        {
            id: 'reflect', label: 'Reflection check', sub: 'style and safety', kind: 'decision', x: 140, y: 660,
            detail: 'A second model call checks the draft before it is sent: direct answers must actually answer, problem hints must stay Socratic, and everything must be safe and on topic. A rejected draft is regenerated once with the feedback, then the latest version is accepted. Error replies skip this check.',
            tech: ['gpt-oss:120b', 'max 1 regeneration'],
        },
        {
            id: 'history', label: 'Save to chat history', sub: 'Postgres checkpointer', kind: 'store', x: 280, y: 780,
            detail: 'The approved reply is appended to the conversation, which LangGraph checkpoints in Postgres per session. That is what lets follow-ups build on earlier turns and old chats reopen from the sidebar.',
            tech: ['LangGraph AsyncPostgresSaver', 'PostgreSQL'],
        },
        {
            id: 'answer', label: 'Answer + sources', sub: 'read aloud on request', kind: 'output', x: 280, y: 880,
            detail: 'The reply comes back with its sources: lecture links that open YouTube at the right second, and book page ranges. The read-aloud button sends it to Kokoro on the server, one sentence group at a time.',
            tech: ['Kokoro-82M (text to speech)', 'KaTeX'],
        },
        {
            id: 'db', label: 'Knowledge base', sub: 'book + 29 lectures', kind: 'store', x: -300, y: 380,
            detail: 'Postgres with pgvector: 1,149 sections split into 4,993 passages with 768-dimension embeddings and a full-text index, plus a concept graph of 4,323 nodes and 11,471 links. See the "Building the knowledge base" tab for how it is made.',
            tech: ['PostgreSQL 16', 'pgvector'],
        },
    ],
    links: [
        { from: 'message', to: 'filters' },
        { from: 'filters', to: 'route' },
        { from: 'route', to: 'search', label: 'concept' },
        { from: 'route', to: 'image', label: 'problem / photo' },
        { from: 'route', to: 'clarify', label: 'unclear' },
        { from: 'search', to: 'direct' },
        { from: 'image', to: 'critique' },
        { from: 'critique', to: 'socratic' },
        { from: 'direct', to: 'reflect' },
        { from: 'socratic', to: 'reflect' },
        { from: 'reflect', to: 'direct', label: 'rejected', dashed: true, fromSide: 'ls', toSide: 'l' },
        { from: 'reflect', to: 'socratic', label: 'rejected', dashed: true, fromSide: 'r', toSide: 'rt' },
        { from: 'reflect', to: 'history', label: 'approved' },
        { from: 'clarify', to: 'history', toSide: 'rt' },
        { from: 'history', to: 'answer' },
        { from: 'db', to: 'search', dashed: true, fromSide: 'r', toSide: 'l' },
    ],
};

export const ingestionFlow: { steps: FlowStep[]; links: FlowLink[] } = {
    steps: [
        {
            id: 'pdf', label: 'Textbook PDF', sub: '242 pages', kind: 'input', x: 0, y: 0,
            detail: 'The CS109 course reader, "Probability for Computer Scientists": 79 web articles printed to one PDF, each restarting its own page numbers.',
            tech: ['PDF'],
        },
        {
            id: 'docling', label: 'Parse pages', sub: 'Docling, 20-page batches', kind: 'local', x: 0, y: 110,
            detail: 'Docling turns each page into Markdown with headings, tables and pictures. Pages with formulas Docling could not decode, or with very little text, are flagged as hard (183 of 242).',
            tech: ['Docling', 'PyMuPDF'],
        },
        {
            id: 'pdfvision', label: 'Read hard pages', sub: '183 pages to LaTeX', kind: 'llm', x: 0, y: 220,
            detail: 'Each hard page is rendered at 150 dpi and transcribed by a vision model into Markdown with LaTeX, recovering the formulas Docling left out.',
            tech: ['gemma4:31b (vision)', 'PyMuPDF rendering'],
        },
        {
            id: 'playlist', label: 'Lecture videos', sub: '29 lectures', kind: 'input', x: 560, y: 0,
            detail: 'The Stanford CS109 (2022) YouTube playlist. Video files are matched to playlist entries by title.',
            tech: ['yt-dlp'],
        },
        {
            id: 'captions', label: 'Captions', sub: 'manual English track', kind: 'local', x: 340, y: 110,
            detail: 'Every lecture has a hand-made English caption track, which is punctuated and spells the terms right, so no speech recognition is needed. Auto captions are the fallback.',
            tech: ['youtube-transcript-api'],
        },
        {
            id: 'slides', label: 'Find the slides', sub: 'keyframes, no camera shots', kind: 'local', x: 620, y: 110,
            detail: 'ffmpeg pulls the keyframes. Frames of the lecturer on camera are dropped by a texture test, and builds of the same slide are merged by comparing which pixels changed, keeping the final build and the times it was on screen.',
            tech: ['ffmpeg', 'NumPy'],
        },
        {
            id: 'slidevision', label: 'Transcribe slides', sub: 'text, tables, LaTeX', kind: 'llm', x: 620, y: 220,
            detail: 'Each kept slide is read by a vision model, and its image is uploaded to Cloudinary under a content hash so it can be shown later.',
            tech: ['gemma4:31b (vision)', 'Cloudinary'],
        },
        {
            id: 'chunk', label: 'Split into sections', sub: '1,149 sections, 4,993 passages', kind: 'local', x: 300, y: 350,
            detail: 'Book text is split at headings into sections of up to 4,000 characters, with passages of up to 1,000 inside them; code and formula blocks are never cut. Lectures are split into transcript windows of about 2.5 to 4 minutes, and each slide becomes a passage of the window where it first appears.',
            tech: ['Python'],
        },
        {
            id: 'context', label: 'Context line', sub: 'one per section', kind: 'llm', x: 300, y: 460,
            detail: 'A short sentence saying where each section sits in the course is written once per section and prepended to its passages before embedding, which helps short passages match the right questions.',
            tech: ['gpt-oss:120b'],
        },
        {
            id: 'embed', label: 'Embed passages', sub: '768-dimension vectors', kind: 'local', x: 120, y: 590,
            detail: 'Every passage is embedded on the CPU with bge-base-en-v1.5, the same model the search uses for questions.',
            tech: ['bge-base-en-v1.5', 'sentence-transformers'],
        },
        {
            id: 'extract', label: 'Extract concepts', sub: '7 node types, 6 link types', kind: 'llm', x: 480, y: 590,
            detail: 'Each section is read for concepts, definitions, theorems, formulas, examples, figures and distributions, and the links between them: prerequisite of, defined in, illustrates, special case of, uses, related to.',
            tech: ['gpt-oss:120b'],
        },
        {
            id: 'resolve', label: 'Merge duplicates', sub: 'checked by the model', kind: 'llm', x: 480, y: 700,
            detail: 'The same idea named in the book and in a lecture becomes one node. Candidate pairs (same type, names that embed close together, or a shared alias) are each confirmed by a yes/no model check; nothing is merged automatically. Result: 4,323 nodes and 11,471 links.',
            tech: ['bge-base-en-v1.5', 'gpt-oss:120b'],
        },
        {
            id: 'store', label: 'Postgres + pgvector', sub: 'passages, vectors, graph', kind: 'store', x: 300, y: 820,
            detail: 'Everything lands in one local Postgres database: sources, sections and passages with their vectors and a full-text index, and the concept graph as node, link and mention tables. Each stage caches its results, so a rerun only redoes what changed.',
            tech: ['PostgreSQL 16', 'pgvector', 'Docker'],
        },
        {
            id: 'retriever', label: 'Retriever', sub: 'used by the tutor', kind: 'output', x: 300, y: 930,
            detail: 'At question time the tutor searches this database (see the other tab). On a 46-question test set the right source is in the top 5 results for 98% of questions.',
            tech: ['hybrid search', 'graph expansion'],
        },
    ],
    links: [
        { from: 'pdf', to: 'docling' },
        { from: 'docling', to: 'pdfvision', label: 'hard pages' },
        { from: 'playlist', to: 'captions' },
        { from: 'playlist', to: 'slides' },
        { from: 'slides', to: 'slidevision' },
        { from: 'pdfvision', to: 'chunk' },
        { from: 'captions', to: 'chunk' },
        { from: 'slidevision', to: 'chunk' },
        { from: 'chunk', to: 'context' },
        { from: 'context', to: 'embed' },
        { from: 'chunk', to: 'extract', fromSide: 'r' },
        { from: 'extract', to: 'resolve' },
        { from: 'embed', to: 'store' },
        { from: 'resolve', to: 'store' },
        { from: 'store', to: 'retriever', dashed: true },
    ],
};
