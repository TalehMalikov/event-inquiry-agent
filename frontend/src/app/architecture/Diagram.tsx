"use client";

import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef } from "react";
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
  slate: "border-slate-200 bg-slate-100/60 text-slate-500",
  zinc: "border-zinc-300 bg-zinc-100/70 text-zinc-600",
  emerald: "border-emerald-200 bg-emerald-50/70 text-emerald-700",
  violet: "border-violet-200 bg-violet-50/70 text-violet-700",
  teal: "border-teal-200 bg-teal-50/70 text-teal-700",
  sky: "border-sky-200 bg-sky-50/70 text-sky-700",
  amber: "border-amber-200 bg-amber-50/70 text-amber-700",
  blue: "border-blue-200 bg-blue-50/70 text-blue-700",
  rose: "border-rose-200 bg-rose-50/70 text-rose-700",
};

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3;
const ZOOM_SPEED = 0.012; // bigger = faster pinch zoom

const CARD_W = 180;
const CARD_H = 56;
const TABLE_W = 200;

type Mark = { dim?: boolean; hot?: boolean };
type CardData = Info & Mark;
type BoxData = { label: string; tone: string };
type TableData = Table & Mark;

// Handles on all four sides; each line uses the sides that face each other (sideFor), so dragging stays tidy.
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
      style={{ width: CARD_W, height: CARD_H }}
      className={`flex cursor-pointer items-center overflow-hidden rounded-xl border bg-white transition-opacity ${
        data.kind === "off" ? "border-dashed border-slate-300 text-slate-400" : "border-slate-200"
      } ${selected || data.hot ? "ring-2 ring-slate-900" : ""} ${data.dim ? "opacity-20" : ""}`}
    >
      <span className={`h-full w-1.5 shrink-0 ${ACCENT[data.kind]}`} />
      <span className="px-2.5 text-xl leading-none" aria-hidden>
        {data.icon}
      </span>
      <span className="truncate pr-2 text-sm font-semibold">{data.title}</span>
      <Sides />
    </div>
  );
}

function GroupBox({ data }: NodeProps<Node<BoxData>>) {
  return (
    <div className={`h-full w-full rounded-2xl border ${TONE[data.tone] ?? TONE.slate}`}>
      <div className="px-3 pt-2 text-[11px] font-semibold uppercase tracking-wider">{data.label}</div>
    </div>
  );
}

function TableCard({ data, selected }: NodeProps<Node<TableData>>) {
  return (
    <div
      style={{ width: TABLE_W }}
      className={`cursor-pointer overflow-hidden rounded-xl border border-sky-200 bg-white transition-opacity ${
        selected || data.hot ? "ring-2 ring-slate-900" : ""
      } ${data.dim ? "opacity-20" : ""}`}
    >
      <div className="bg-sky-600 px-3 py-1.5 font-mono text-sm font-semibold text-white">{data.title}</div>
      <ul className="font-mono text-[11px] text-slate-600">
        {data.cols.map((c) => (
          <li key={c} className="border-t border-slate-100 px-3 py-1">
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

function ZoomButtons() {
  const { zoomTo, getZoom, fitView } = useReactFlow();
  const step = (f: number) => zoomTo(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, getZoom() * f)), { duration: 180 });
  const btn =
    "flex h-10 w-10 items-center justify-center rounded-xl bg-white text-lg font-semibold text-slate-700 shadow ring-1 ring-slate-200 hover:bg-slate-50 active:scale-95";
  return (
    <div className="absolute bottom-3 left-3 z-10 flex flex-col gap-2">
      <button className={btn} onClick={() => step(1.8)} aria-label="Zoom in">
        +
      </button>
      <button className={btn} onClick={() => step(1 / 1.8)} aria-label="Zoom out">
        −
      </button>
      <button className={btn} onClick={() => fitView({ duration: 500, padding: 0.06 })} aria-label="Show all">
        ⤢
      </button>
    </div>
  );
}

function Canvas({ items, boxes, tables, links, highlight, selected, onSelect, height }: Props) {
  const [nodes, , onNodesChange] = useNodesState(initialNodes(items, boxes, tables));
  const { fitView, getViewport, setViewport } = useReactFlow();
  const wrap = useRef<HTMLDivElement>(null);

  // Fast pinch zoom. Touchpad pinch (and Ctrl + wheel) arrives as many tiny wheel events, which the default
  // handler turns into slow zooming; here each event zooms proportionally, around the cursor.
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return; // two-finger scroll: React Flow pans
      e.preventDefault();
      e.stopPropagation();
      const v = getViewport();
      const delta = e.deltaMode === 1 ? e.deltaY * 20 : e.deltaY;
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom * Math.exp(-delta * ZOOM_SPEED)));
      const r = el.getBoundingClientRect();
      const px = e.clientX - r.left;
      const py = e.clientY - r.top;
      setViewport({ zoom, x: px - ((px - v.x) * zoom) / v.zoom, y: py - ((py - v.y) * zoom) / v.zoom });
    };
    el.addEventListener("wheel", onWheel, { passive: false, capture: true });
    return () => el.removeEventListener("wheel", onWheel, { capture: true });
  }, [getViewport, setViewport]);

  // The camera follows: tapping a card or a flow step glides to it; clearing shows everything again
  const focusKey = highlight ? [...highlight.nodes].sort().join(",") : "";
  useEffect(() => {
    const t = setTimeout(() => {
      if (focusKey) fitView({ nodes: focusKey.split(",").map((id) => ({ id })), duration: 600, padding: 0.35, maxZoom: 1.3 });
      else fitView({ duration: 600, padding: 0.06 });
    }, 30);
    return () => clearTimeout(t);
  }, [focusKey, fitView]);

  // Centers in diagram coordinates (children are stored relative to their group)
  const centers = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const rows = new Map((tables ?? []).map((t) => [t.id, t.cols.length]));
    const out = new Map<string, XY>();
    for (const n of nodes) {
      if (n.type === "box") continue;
      const parent = n.parentId ? byId.get(n.parentId) : undefined;
      const x = n.position.x + (parent?.position.x ?? 0);
      const y = n.position.y + (parent?.position.y ?? 0);
      const r = rows.get(n.id);
      out.set(n.id, r === undefined ? { x: x + CARD_W / 2, y: y + CARD_H / 2 } : { x: x + TABLE_W / 2, y: y + 18 + r * 12 });
    }
    return out;
  }, [nodes, tables]);

  const shownNodes = useMemo(
    () =>
      nodes.map((n) => {
        const base = { ...n, selected: n.id === selected };
        if (n.type === "box" || !highlight) return base;
        return { ...base, data: { ...n.data, dim: !highlight.nodes.has(n.id), hot: highlight.nodes.has(n.id) } };
      }),
    [nodes, highlight, selected],
  );

  const edges: Edge[] = useMemo(
    () =>
      links.map((l) => {
        const a = centers.get(l.from) ?? { x: 0, y: 0 };
        const b = centers.get(l.to) ?? { x: 0, y: 0 };
        const [sh, th] = sideFor(a, b);
        const hot = highlight?.links.has(l.id) ?? false;
        const dim = highlight ? !hot : false;
        const color = hot ? "#0f172a" : "#cbd5e1";
        return {
          id: l.id,
          source: l.from,
          target: l.to,
          sourceHandle: sh,
          targetHandle: th,
          label: hot ? l.label : undefined, // words only on the lines that matter right now
          animated: hot, // moving dashes only on lit lines (constant animation slows zooming)
          zIndex: hot ? 10 : 0,
          style: {
            stroke: color,
            strokeWidth: hot ? 2.5 : 1.3,
            strokeDasharray: l.off ? "5 5" : undefined,
            opacity: dim ? 0.15 : 1,
          },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
          labelStyle: { fontSize: 11, fill: "#0f172a", fontWeight: 600 },
          labelBgStyle: { fill: "#ffffff" },
          labelBgPadding: [4, 2] as [number, number],
          labelShowBg: true,
        };
      }),
    [links, centers, highlight],
  );

  return (
    <div ref={wrap} className={`${height ?? "h-[70vh] min-h-[460px]"} relative w-full overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200`}>
      <ReactFlow
        nodes={shownNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_, n) => n.type !== "box" && onSelect(n.id === selected ? null : n.id)}
        onPaneClick={() => onSelect(null)}
        fitView
        fitViewOptions={{ padding: 0.06 }}
        // Touchpad: two fingers move the map, pinch zooms. Mouse: drag to move, Ctrl + wheel or the buttons to zoom.
        panOnScroll
        panOnScrollSpeed={0.9}
        zoomOnScroll={false}
        zoomOnPinch // phone pinch; touchpad pinch is caught first by the faster handler above
        zoomOnDoubleClick
        panOnDrag
        minZoom={MIN_ZOOM}
        maxZoom={MAX_ZOOM}
        nodesConnectable={false}
        proOptions={{ hideAttribution: false }}
      >
        <Background gap={24} color="#eef2f7" />
      </ReactFlow>
      <ZoomButtons />
    </div>
  );
}

export default function Diagram(props: Props) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
