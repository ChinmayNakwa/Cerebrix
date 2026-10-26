'use client';
import { memo, useMemo, useState } from 'react';
import {
    ReactFlow, Controls, Background, BackgroundVariant, Handle, Position, MarkerType,
    type Edge, type Node, type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Card, Tag } from 'antd';
import { MousePointerClick } from 'lucide-react';
import { kindStyle, type FlowLink, type FlowStep } from '@/src/lib/architecture';

type StepNode = Node<{ step: FlowStep; active: boolean; dimmed: boolean }, 'step'>;

const handleClass = 'opacity-0! w-1! h-1! min-w-0! min-h-0! border-0!';

const StepBox = memo(function StepBox({ data }: NodeProps<StepNode>) {
    const { step, active, dimmed } = data;
    const color = kindStyle[step.kind].color;
    return (
        <div
            className={`w-[210px] rounded-xl border bg-[#0f0f12] px-3 py-2 cursor-pointer transition-all ${dimmed ? 'opacity-40' : ''}`}
            style={{ borderColor: active ? color : 'rgba(255,255,255,0.12)', boxShadow: active ? `0 0 0 2px ${color}55, 0 0 24px ${color}33` : undefined }}
        >
            <Handle type="target" position={Position.Top} id="t" className={handleClass} />
            <Handle type="target" position={Position.Left} id="l" className={handleClass} />
            <Handle type="target" position={Position.Right} id="rt" className={handleClass} />
            <div className="flex items-center gap-2">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
                <span className="text-[13px] font-semibold text-zinc-100 leading-tight">{step.label}</span>
            </div>
            <div className="mt-0.5 pl-4 text-[11px] text-zinc-500 leading-tight">{step.sub}</div>
            <Handle type="source" position={Position.Bottom} id="b" className={handleClass} />
            <Handle type="source" position={Position.Left} id="ls" className={handleClass} />
            <Handle type="source" position={Position.Right} id="r" className={handleClass} />
        </div>
    );
});

const nodeTypes = { step: StepBox };

type FlowDiagramProps = { steps: FlowStep[]; links: FlowLink[]; height?: number };

export default function FlowDiagram({ steps, links, height = 720 }: FlowDiagramProps) {
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const selected = steps.find((s) => s.id === selectedId) ?? null;

    // The selected step and its direct neighbours stay lit; everything else dims
    const neighbours = useMemo(() => {
        if (!selectedId) return null;
        const ids = new Set([selectedId]);
        links.forEach((l) => { if (l.from === selectedId) ids.add(l.to); if (l.to === selectedId) ids.add(l.from); });
        return ids;
    }, [selectedId, links]);

    const nodes: StepNode[] = useMemo(() => steps.map((step) => ({
        id: step.id,
        type: 'step',
        position: { x: step.x, y: step.y },
        data: { step, active: step.id === selectedId, dimmed: !!neighbours && !neighbours.has(step.id) },
    })), [steps, selectedId, neighbours]);

    const edges: Edge[] = useMemo(() => links.map((l, i) => {
        const touches = selectedId && (l.from === selectedId || l.to === selectedId);
        const stroke = touches ? '#a5b4fc' : l.dashed ? '#52525b' : '#71717a';
        return {
            id: `e${i}`,
            source: l.from,
            target: l.to,
            sourceHandle: l.fromSide ?? 'b',
            targetHandle: l.toSide ?? 't',
            label: l.label,
            type: 'smoothstep',
            animated: !!touches,
            style: { stroke, strokeWidth: touches ? 2 : 1.4, strokeDasharray: l.dashed ? '5 4' : undefined, opacity: neighbours && !touches ? 0.3 : 1 },
            markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 16, height: 16 },
            labelStyle: { fill: '#d4d4d8', fontSize: 11 },
            labelBgStyle: { fill: '#18181b' },
            labelBgPadding: [6, 3] as [number, number],
            labelBgBorderRadius: 6,
        };
    }), [links, selectedId, neighbours]);

    return (
        <div className="flex flex-col gap-4">
            <div className="glass rounded-2xl overflow-hidden h-[520px] md:h-[var(--flow-height)]" style={{ '--flow-height': `${height}px` } as React.CSSProperties}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    nodeTypes={nodeTypes}
                    colorMode="dark"
                    fitView
                    // On phones the whole diagram would be unreadably small, so it opens at a readable zoom to pan around
                    fitViewOptions={{ padding: 0.08, minZoom: 0.5 }}
                    minZoom={0.3}
                    maxZoom={1.6}
                    nodesDraggable={false}
                    nodesConnectable={false}
                    edgesFocusable={false}
                    zoomOnScroll={false}
                    preventScrolling={false}
                    onNodeClick={(_, node) => setSelectedId(node.id === selectedId ? null : node.id)}
                    onPaneClick={() => setSelectedId(null)}
                    style={{ background: 'transparent' }}
                >
                    <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#27272a" />
                    <Controls showInteractive={false} position="bottom-right" />
                </ReactFlow>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-4">
                <Card size="small" className="glass!">
                    {selected ? (
                        <>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="h-2.5 w-2.5 rounded-full" style={{ background: kindStyle[selected.kind].color }} />
                                <span className="text-xs uppercase tracking-wider text-zinc-500">{kindStyle[selected.kind].name}</span>
                            </div>
                            <h3 className="text-lg font-bold text-white mb-2">{selected.label}</h3>
                            <p className="text-sm text-zinc-300 leading-relaxed mb-3">{selected.detail}</p>
                            <div className="flex flex-wrap gap-1.5">
                                {selected.tech.map((t) => <Tag key={t} className="m-0!">{t}</Tag>)}
                            </div>
                        </>
                    ) : (
                        <div className="flex items-start gap-3 text-sm text-zinc-400">
                            <MousePointerClick size={18} className="mt-0.5 shrink-0 text-indigo-400" />
                            <span>Click a step to see what it does and what runs it. Drag to pan; use the buttons to zoom.</span>
                        </div>
                    )}
                </Card>

                <Card size="small" className="glass!" title={<span className="text-xs uppercase tracking-wider text-zinc-500">Legend</span>}>
                    <div className="grid grid-cols-1 gap-1.5 text-sm text-zinc-300">
                        {Object.values(kindStyle).map((k) => (
                            <div key={k.name} className="flex items-center gap-2">
                                <span className="h-2.5 w-2.5 rounded-full" style={{ background: k.color }} />{k.name}
                            </div>
                        ))}
                        <div className="flex items-center gap-2 text-zinc-400">
                            <span className="w-5 border-t border-dashed border-zinc-500" />Optional or reads data
                        </div>
                    </div>
                </Card>
            </div>
        </div>
    );
}
