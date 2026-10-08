'use client';
import { memo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

const remarkPlugins = [remarkMath];
const rehypePlugins = [rehypeKatex];

// react-markdown passes the hast `node` prop, which must not reach the DOM element.
function withoutNode<T extends { node?: unknown }>(props: T) {
  const rest = { ...props };
  delete rest.node;
  return rest;
}

const components: Components = {
  p: (props) => <p className="mb-4 last:mb-0" {...withoutNode(props)} />,
  h1: (props) => <h1 className="text-2xl font-bold mb-4" {...withoutNode(props)} />,
  h2: (props) => <h2 className="text-xl font-bold mb-3" {...withoutNode(props)} />,
  ul: (props) => <ul className="list-disc pl-5 mb-4" {...withoutNode(props)} />,
  ol: (props) => <ol className="list-decimal pl-5 mb-4" {...withoutNode(props)} />,
  code: (props) => (
    <code className="bg-black/30 px-1 py-0.5 rounded text-accent font-mono text-sm" {...withoutNode(props)} />
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
