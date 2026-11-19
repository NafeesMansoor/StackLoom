// Loaded on demand: Cytoscape.js and the drawing of a CodeCortex graph.
import cytoscape, { type Core } from "cytoscape";
import { useEffect, useRef } from "react";

export interface GNode { id: string; name: string; kind: string; file: string; line: number; centrality: number; degree: number; hotspot: boolean; cluster: number }
export interface GEdge { id: string; source: string; target: string; kind: string }

const KIND_COLOR: Record<string, string> = {
  File: "#4285d4", Module: "#4285d4", Namespace: "#4285d4", Class: "#16a36a", Struct: "#16a36a", Interface: "#2a6dbb",
  Function: "#e6a23c", Method: "#c98a2e", Endpoint: "#dc5757", Test: "#8a93b7", Type: "#2a6dbb", Enum: "#c98a2e", Constant: "#c98a2e",
};
const EDGE_COLOR: Record<string, string> = { CALLS: "#e6a23c", IMPORTS_FROM: "#4285d4", INHERITS: "#16a36a", CONTAINS: "#b9bfcc", TESTS: "#8a93b7" };

export const LAYOUTS: Record<string, cytoscape.LayoutOptions> = {
  force: { name: "cose", animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 70, numIter: 800 } as cytoscape.LayoutOptions,
  hierarchy: { name: "breadthfirst", directed: true, spacingFactor: 1.1, animate: false },
  circle: { name: "circle", animate: false },
  grid: { name: "grid", animate: false },
};

export function GraphCanvas({ nodes, edges, layout, selected, highlight, onSelect, onReady, dark }: {
  nodes: GNode[]; edges: GEdge[]; layout: string; selected: string | null; highlight: "none" | "hotspots" | "neighbours";
  onSelect: (id: string | null) => void; onReady: (cy: Core) => void; dark: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!box.current) return;
    const max = Math.max(...nodes.map((n) => n.centrality), 0.000001);
    const cy = cytoscape({
      container: box.current,
      elements: [
        ...nodes.map((n) => ({ data: { ...n, label: n.name, size: 14 + 34 * Math.sqrt(n.centrality / max), color: KIND_COLOR[n.kind] ?? "#788197" } })),
        ...edges.map((e) => ({ data: { ...e, color: EDGE_COLOR[e.kind] ?? "#b9bfcc" } })),
      ],
      style: [
        { selector: "node", style: { "background-color": "data(color)", width: "data(size)", height: "data(size)", label: "data(label)",
          "font-size": 10, color: dark ? "#e7e9ee" : "#1b2a44", "text-valign": "bottom", "text-margin-y": 3, "min-zoomed-font-size": 7,
          "border-width": 0 } },
        { selector: "node[?hotspot]", style: { "border-width": 3, "border-color": "#dc5757" } },
        { selector: "edge", style: { width: 1.2, "line-color": "data(color)", "target-arrow-color": "data(color)", "target-arrow-shape": "triangle",
          "arrow-scale": 0.7, "curve-style": "bezier", opacity: 0.75 } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: "node:selected", style: { "border-width": 4, "border-color": dark ? "#9db8e8" : "#1f3a68" } },
      ],
      layout: LAYOUTS[layout] ?? LAYOUTS.force,
      wheelSensitivity: 0.25,
      minZoom: 0.05,
      maxZoom: 4,
    });
    cy.on("tap", "node", (e) => onSelect(e.target.id()));
    cy.on("tap", (e) => { if (e.target === cy) onSelect(null); });
    cyRef.current = cy;
    onReady(cy);
    return () => cy.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, dark]);

  useEffect(() => { cyRef.current?.layout(LAYOUTS[layout] ?? LAYOUTS.force).run(); }, [layout]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass("faded");
    cy.nodes().unselect();
    if (selected) {
      const n = cy.getElementById(selected);
      if (n.nonempty()) {
        n.select();
        if (highlight === "neighbours") cy.elements().difference(n.closedNeighborhood()).addClass("faded");
        cy.animate({ center: { eles: n }, duration: 250 });
      }
    }
    if (highlight === "hotspots") cy.elements().difference(cy.nodes("[?hotspot]")).addClass("faded");
  }, [selected, highlight]);

  return <div ref={box} className="graph-canvas" role="img" aria-label="Interactive code graph. Use the search and the list to reach symbols by keyboard." />;
}
