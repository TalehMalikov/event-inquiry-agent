"use client";

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { Box, Info, Kind, Link, Table } from "./data";

// ---------- Looks ----------

const ACCENT: Record<Kind, string> = {
  person: "bg-slate-500",
  vercel: "bg-zinc-900",
  ext: "bg-indigo-500",
  data: "bg-sky-500",
  ai: "bg-teal-500",
  off: "bg-slate-300",
  code: "bg-slate-400",
};

const TONE: Record<string, string> = {
  slate: "border-slate-300 bg-slate-100/70 text-slate-500",
  zinc: "border-zinc-400 bg-zinc-100/80 text-zinc-600",
  emerald: "border-emerald-300 bg-emerald-50/80 text-emerald-700",
  violet: "border-violet-300 bg-violet-50/80 text-violet-700",
  teal: "border-teal-300 bg-teal-50/80 text-teal-700",
  sky: "border-sky-300 bg-sky-50/80 text-sky-700",
  amber: "border-amber-300 bg-amber-50/80 text-amber-700",
  blue: "border-blue-300 bg-blue-50/80 text-blue-700",
  rose: "border-rose-300 bg-rose-50/80 text-rose-700",
};

const CARD_W = 220;
const CARD_H = 76;
const TABLE_W = 260;

type Mark = { dim?: boolean; hot?: boolean };
type CardData = Info & Mark;
type BoxData = { label: string; tone: string };
type TableData = Table & Mark;

// Handles on all four sides; each line picks the sides that face each other (see sideFor), so dragging stays tidy.
function Sides() {
  return (
    <>
      {(
        [
          ["l", Position.Left],
          ["r", Position.Right],
          ["t", Position.Top],
          ["b", Position.Bottom],
        ] as const
      ).map(([id, pos]) => (
        <span key={id}>
          <Handle id={`s-${id}`} type="source" position={pos} className="!h-1 !w-1 !border-0 !bg-transparent" />
          <Handle id={`t-${id}`} type="target" position={pos} className="!h-1 !w-1 !border-0 !bg-transparent" />
        </span>
      ))}
    </>
  );
}

function Card({ data, selected }: NodeProps<Node<CardData>>) {
  return (
    <div
      style={{ width: CARD_W, minHeight: CARD_H }}
      className={`flex overflow-hidden rounded-xl border bg-white text-left shadow-sm transition ${
        data.kind === "off" ? "border-dashed border-slate-300" : "border-slate-200"
      } ${selected || data.hot ? "ring-2 ring-slate-900" : ""} ${data.dim ? "opacity-25" : ""}`}
    >
      <span className={`w-1.5 shrink-0 ${ACCENT[data.kind]}`} />
      <div className="flex min-w-0 flex-1 items-start gap-2 p-2.5">
        <span className="text-xl leading-none" aria-hidden>
          {data.icon}
        </span>
        <div className="min-w-0">
          <div className={`text-[13px] font-semibold leading-tight ${data.kind === "off" ? "text-slate-400" : ""}`}>
            {data.title}
          </div>
          <div className="mt-0.5 text-[11px] leading-snug text-slate-500">{data.tech}</div>
        </div>
      </div>
      <Sides />
    </div>
  );
}

function GroupBox({ data }: NodeProps<Node<BoxData>>) {
  return (
    <div className={`h-full w-full rounded-2xl border-2 ${TONE[data.tone] ?? TONE.slate}`}>
      <div className="px-3 pt-2 text-[11px] font-semibold uppercase tracking-wide">{data.label}</div>
    </div>
  );
}

function TableCard({ data, selected }: NodeProps<Node<TableData>>) {
  return (
    <div
      style={{ width: TABLE_W }}
      className={`overflow-hidden rounded-xl border border-sky-200 bg-white shadow-sm ${
        selected || data.hot ? "ring-2 ring-slate-900" : ""
      } ${data.dim ? "opacity-25" : ""}`}
    >
      <div className="bg-sky-600 px-3 py-1.5 text-white">
        <div className="font-mono text-[13px] font-semibold">{data.title}</div>
        <div className="text-[10px] opacity-80">{data.note}</div>
      </div>
      <ul className="divide-y divide-slate-100 font-mono text-[11px]">
        {data.cols.map((c) => (
          <li key={c} className={`px-3 py-1 ${/PK|FK/.test(c) ? "text-sky-700" : "text-slate-600"}`}>
            {c}
          </li>
        ))}
      </ul>
      <Sides />
    </div>
  );
}

const nodeTypes = { card: Card, box: GroupBox, table: TableCard };

// ---------- Geometry ----------

type XY = { x: number; y: number };

function sideFor(a: XY, b: XY): [string, string] {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  if (Math.abs(dx) >= Math.abs(dy) * 0.6) return dx >= 0 ? ["s-r", "t-l"] : ["s-l", "t-r"];
  return dy >= 0 ? ["s-b", "t-t"] : ["s-t", "t-b"];
}

export type Highlight = { nodes: Set<string>; links: Set<string> } | null;

type Props = {
  items?: (Info & { id: string; parent?: string; x: number; y: number })[];
  boxes?: Box[];
  tables?: Table[];
  links: Link[];
  highlight: Highlight;
  selected: string | null;
  onSelect: (id: string | null) => void;
  height?: string;
};

function initialNodes(items: Props["items"], boxes: Props["boxes"], tables: Props["tables"]): Node[] {
  const out: Node[] = [];
  for (const b of boxes ?? []) {
    out.push({
      id: b.id,
      type: "box",
      position: { x: b.x, y: b.y },
      data: { label: b.label, tone: b.tone },
      style: { width: b.w, height: b.h },
      selectable: false,
      zIndex: -1,
    });
  }
  for (const it of items ?? []) {
    out.push({
      id: it.id,
      type: "card",
      position: { x: it.x, y: it.y },
      data: { ...it },
      ...(it.parent ? { parentId: it.parent, extent: "parent" as const } : {}),
    });
  }
  for (const t of tables ?? []) {
    out.push({ id: t.id, type: "table", position: { x: t.x, y: t.y }, data: { ...t } });
  }
  return out;
}

export default function Diagram({ items, boxes, tables, links, highlight, selected, onSelect, height }: Props) {
  const [nodes, , onNodesChange] = useNodesState(initialNodes(items, boxes, tables));

  // Centers in diagram coordinates (children are stored relative to their group)
  const centers = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const tableRows = new Map((tables ?? []).map((t) => [t.id, t.cols.length]));
    const out = new Map<string, XY>();
    for (const n of nodes) {
      if (n.type === "box") continue;
      const parent = n.parentId ? byId.get(n.parentId) : undefined;
      const x = n.position.x + (parent?.position.x ?? 0);
      const y = n.position.y + (parent?.position.y ?? 0);
      const rows = tableRows.get(n.id);
      const w = rows === undefined ? CARD_W : TABLE_W;
      const h = rows === undefined ? CARD_H : 44 + rows * 22;
      out.set(n.id, { x: x + w / 2, y: y + h / 2 });
    }
    return out;
  }, [nodes, tables]);

  const shownNodes = useMemo(
    () =>
      nodes.map((n) =>
        n.type === "box" || !highlight
          ? n
          : { ...n, data: { ...n.data, dim: !highlight.nodes.has(n.id), hot: highlight.nodes.has(n.id) } },
      ),
    [nodes, highlight],
  );

  const edges: Edge[] = useMemo(
    () =>
      links.map((l) => {
        const a = centers.get(l.from) ?? { x: 0, y: 0 };
        const b = centers.get(l.to) ?? { x: 0, y: 0 };
        const [sh, th] = sideFor(a, b);
        const hot = highlight?.links.has(l.id) ?? false;
        const dim = highlight ? !hot : false;
        const color = hot ? "#0f172a" : "#94a3b8";
        return {
          id: l.id,
          source: l.from,
          target: l.to,
          sourceHandle: sh,
          targetHandle: th,
          label: l.label,
          animated: hot || l.off,
          zIndex: hot ? 10 : 0,
          style: {
            stroke: color,
            strokeWidth: hot ? 2.5 : 1.4,
            strokeDasharray: l.off ? "5 5" : undefined,
            opacity: dim ? 0.12 : 1,
          },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
          labelStyle: { fontSize: 10, fill: hot ? "#0f172a" : "#64748b", fontWeight: hot ? 600 : 400 },
          labelBgStyle: { fill: "#ffffff", fillOpacity: dim ? 0.2 : 0.9 },
          labelBgPadding: [4, 2] as [number, number],
          labelShowBg: true,
        };
      }),
    [links, centers, highlight],
  );

  return (
    <div className={`${height ?? "h-[68vh] min-h-[460px]"} w-full overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200`}>
      <ReactFlow
        nodes={shownNodes.map((n) => ({ ...n, selected: n.id === selected }))}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_, n) => n.type !== "box" && onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        minZoom={0.15}
        maxZoom={2}
        nodesConnectable={false}
        elementsSelectable
      >
        <Background gap={24} color="#e2e8f0" />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable className="!hidden sm:!block" nodeStrokeWidth={2} />
      </ReactFlow>
    </div>
  );
}
