'use client';
import { memo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

const remarkPlugins = [remarkMath];
const rehypePlugins = [rehypeKatex];

const components: Components = {
  p: ({ node, ...props }) => <p className="mb-4 last:mb-0" {...props} />,
  h1: ({ node, ...props }) => <h1 className="text-2xl font-bold mb-4" {...props} />,
  h2: ({ node, ...props }) => <h2 className="text-xl font-bold mb-3" {...props} />,
  ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-4" {...props} />,
  ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-4" {...props} />,
  code: ({ node, ...props }) => (
    <code className="bg-black/30 px-1 py-0.5 rounded text-accent font-mono text-sm" {...props} />
  ),
};

function MathRenderer({ content }: { content: string }) {
  return (
    <div className="text-sm md:text-base leading-relaxed break-words">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MathRenderer);
