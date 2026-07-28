import { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import socket from '../utils/socket';

const MAX_VISIBLE_NODES = 200;
const TICK_THROTTLE_MS = 33;

const ProjectTreeViz = () => {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const [treeData, setTreeData] = useState(null);
  const [tooltip, setTooltip] = useState({ show: false, x: 0, y: 0, content: '' });
  const [nodeStats, setNodeStats] = useState({ visible: 0, total: 0, capped: false });
  const [expanding, setExpanding] = useState(false);
  const simulationRef = useRef(null);
  const zoomRef = useRef(null);
  const rootRef = useRef(null);
  const expandCacheRef = useRef(new Map());

  useEffect(() => {
    fetch('/api/project-tree')
      .then(res => res.json())
      .then(data => setTreeData(data))
      .catch(err => console.error('Failed to fetch project tree:', err));

    socket.on('project_tree', (data) => {
      expandCacheRef.current.clear();
      setTreeData(data);
    });

    return () => socket.off('project_tree');
  }, []);

  const fetchChildren = useCallback(async (path) => {
    if (expandCacheRef.current.has(path)) {
      return expandCacheRef.current.get(path);
    }
    try {
      setExpanding(true);
      const res = await fetch(`/api/project-tree/expand?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      expandCacheRef.current.set(path, data);
      setExpanding(false);
      return data;
    } catch {
      setExpanding(false);
      return null;
    }
  }, []);

  useEffect(() => {
    if (!treeData || !svgRef.current || !containerRef.current) return;

    const container = containerRef.current;
    const width = container.clientWidth || 400;
    const height = container.clientHeight || 300;

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height);

    const zoomLayer = svg.append('g');
    const g = zoomLayer.append('g');

    const zoom = d3.zoom()
      .scaleExtent([0.3, 3])
      .on('zoom', (event) => {
        zoomLayer.attr('transform', event.transform);
      });

    svg.call(zoom);
    zoomRef.current = zoom;

    svg.call(zoom.transform, d3.zoomIdentity
      .translate(width / 2, height / 2)
      .scale(0.5)
      .translate(-width / 2, -height / 2));

    function convertToHierarchy(data, depth = 0) {
      if (!data.children) {
        return { ...data };
      }
      const node = {
        ...data,
        children: data.children.map(child => convertToHierarchy(child, depth + 1))
      };
      if (depth >= 2 && node.children && node.children.length > 0) {
        node._collapsed_children = node.children;
        node.children = null;
      }
      return node;
    }

    const root = d3.hierarchy(convertToHierarchy(treeData));

    function countAll(d) {
      let count = 1;
      if (d.children) d.children.forEach(c => { count += countAll(c); });
      if (d.data._collapsed_children) d.data._collapsed_children.forEach(c => { count += countAll({ data: c, depth: d.depth + 1 }); });
      return count;
    }
    const totalCount = countAll(root);

    function getVisibleNodes() {
      const nodes = [];
      function walk(d) {
        nodes.push(d);
        if (d.children) d.children.forEach(walk);
      }
      walk(root);
      return nodes;
    }

    let visibleNodes = getVisibleNodes();
    let capped = visibleNodes.length > MAX_VISIBLE_NODES;
    setNodeStats({ visible: Math.min(visibleNodes.length, MAX_VISIBLE_NODES), total: totalCount, capped });

    const nodes = capped ? visibleNodes.slice(0, MAX_VISIBLE_NODES) : visibleNodes;
    const links = [];
    nodes.forEach(d => {
      if (d.parent && nodes.includes(d.parent)) {
        links.push({ source: d.parent, target: d });
      }
    });

    const simulation = d3.forceSimulation(nodes)
      .alphaDecay(0.02)
      .force('link', d3.forceLink(links)
        .id(d => d.data.name)
        .distance(40))
      .force('charge', d3.forceManyBody().strength(-150))
      .force('collision', d3.forceCollide().radius(20))
      .force('r', d3.forceRadial(
        d => d.depth * 55,
        width / 2,
        height / 2
      ).strength(0.5));

    simulationRef.current = simulation;
    rootRef.current = root;

    const linkSel = g.append('g')
      .attr('class', 'links')
      .selectAll('path')
      .data(links)
      .join('path')
      .attr('fill', 'none')
      .attr('stroke', '#00FFFF')
      .attr('stroke-opacity', 0.4)
      .attr('stroke-width', 2);

    const nodeSel = g.append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended));

    nodeSel.each(function (d) {
      const isFolder = d.data.children !== null || d.data.truncated;
      const group = d3.select(this);

      if (isFolder) {
        group.append('circle')
          .attr('r', 8)
          .attr('fill', d.data.truncated ? '#FF6B00' : '#00FFFF')
          .attr('stroke', d.data.truncated ? '#FF6B00' : '#00FFFF')
          .attr('stroke-width', 2)
          .style('filter', `drop-shadow(0 0 4px ${d.data.truncated ? '#FF6B00' : '#00FFFF'})`);
      } else {
        group.append('circle')
          .attr('r', 4)
          .attr('fill', '#FFD700')
          .attr('stroke', '#FFD700')
          .attr('stroke-width', 1)
          .style('filter', 'drop-shadow(0 0 3px #FFD700)');
      }

      if (d.data.truncated && d.data.children_count > 0) {
        group.append('text')
          .text(`+${d.data.children_count}`)
          .attr('x', -4)
          .attr('y', -12)
          .attr('fill', '#FF6B00')
          .attr('font-size', '7px')
          .attr('font-family', 'Orbitron, monospace')
          .attr('text-anchor', 'middle')
          .style('pointer-events', 'none');
      }
    });

    nodeSel.append('text')
      .text(d => d.data.name)
      .attr('x', 12)
      .attr('y', 4)
      .attr('fill', d => d.data.children || d.data.truncated ? '#888888' : '#555555')
      .attr('font-size', '9px')
      .attr('font-family', 'Orbitron, monospace')
      .style('pointer-events', 'none')
      .style('opacity', 0);

    nodeSel.on('mouseenter', (event, d) => {
      d3.select(event.currentTarget).select('text').style('opacity', 1);
      const rect = container.getBoundingClientRect();
      const label = d.data.truncated
        ? `${d.data.path} [+${d.data.children_count} items — click to expand]`
        : `${d.data.path || d.data.name}${d.data.size ? ` (${formatSize(d.data.size)})` : ''}`;
      setTooltip({
        show: true,
        x: event.clientX - rect.left,
        y: event.clientY - rect.top - 40,
        content: label
      });
    });

    nodeSel.on('mouseleave', (event) => {
      d3.select(event.currentTarget).select('text').style('opacity', 0);
      setTooltip({ show: false, x: 0, y: 0, content: '' });
    });

    nodeSel.on('click', async (event, d) => {
      event.stopPropagation();

      if (d.data.truncated) {
        const subtree = await fetchChildren(d.data.path);
        if (!subtree) return;

        d.data.children = subtree.children || [];
        d.data._collapsed_children = null;
        d.data.truncated = false;
        d.data.children_count = undefined;
        d.data._expanded_subtree = subtree;
        setTreeData({ ...treeData });
        return;
      }

      if (d.data.children && d.data.children.length > 0) {
        d.data._collapsed_children = d.data.children;
        d.data.children = null;
      } else if (d.data._collapsed_children) {
        d.data.children = d.data._collapsed_children;
        d.data._collapsed_children = null;
      }
      setTreeData({ ...treeData });
    });

    let lastTickTime = 0;
    function tick(timestamp) {
      if (timestamp - lastTickTime < TICK_THROTTLE_MS) return;
      lastTickTime = timestamp;

      const time = timestamp * 0.001;
      const breathScale = 1 + Math.sin(time * 0.5) * 0.10;
      g.attr('transform', `translate(${width / 2}, ${height / 2}) scale(${breathScale}) translate(${-width / 2}, ${-height / 2})`);

      linkSel.attr('d', d => {
        const sx = d.source.x, sy = d.source.y;
        const tx = d.target.x, ty = d.target.y;
        const mx = (sx + tx) / 2, my = (sy + ty) / 2;
        return `M${sx},${sy}Q${mx},${my} ${tx},${ty}`;
      });

      nodeSel.attr('transform', d => {
        const swayX = Math.sin(time + d.depth * 0.3) * 5 * d.depth * 0.1;
        const swayY = Math.cos(time + d.depth * 0.2) * 3 * d.depth * 0.1;
        return `translate(${d.x + swayX},${d.y + swayY})`;
      });
    }

    simulation.on('tick', tick);

    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event, d) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }

    return () => {
      simulation.stop();
    };
  }, [treeData, fetchChildren]);

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const handleZoomIn = () => {
    if (svgRef.current && zoomRef.current) {
      d3.select(svgRef.current).transition().call(zoomRef.current.scaleBy, 1.3);
    }
  };

  const handleZoomOut = () => {
    if (svgRef.current && zoomRef.current) {
      d3.select(svgRef.current).transition().call(zoomRef.current.scaleBy, 0.7);
    }
  };

  const handleFitToView = () => {
    if (svgRef.current && zoomRef.current && containerRef.current) {
      const width = containerRef.current.clientWidth;
      const height = containerRef.current.clientHeight;
      d3.select(svgRef.current).transition().call(
        zoomRef.current.transform,
        d3.zoomIdentity.translate(width / 2, height / 2).scale(0.5).translate(-width / 2, -height / 2)
      );
    }
  };

  const handleCollapseAll = useCallback(() => {
    if (!rootRef.current) return;
    function collapseNode(d) {
      if (d.depth >= 1 && d.data.children && d.data.children.length > 0) {
        d.data._collapsed_children = d.data.children;
        d.data.children = null;
      }
      if (d.children) d.children.forEach(collapseNode);
    }
    rootRef.current.children?.forEach(collapseNode);
    setTreeData({ ...treeData });
  }, [treeData]);

  return (
    <div
      ref={containerRef}
      id="project-viz-panel"
      className="relative w-[500px] h-[600px] overflow-hidden rounded"
    >
      <svg ref={svgRef} className="w-full h-full bg-[#0a0a0a]" />

      {expanding && (
        <div className="absolute top-2 left-2 px-2 py-1 text-[9px] text-amber-400 bg-black/80 rounded border border-amber-400/30 font-mono">
          Loading...
        </div>
      )}

      {nodeStats.total > 0 && (
        <div className="absolute top-2 left-2 px-2 py-1 text-[9px] bg-black/80 rounded border font-mono"
          style={{ borderColor: nodeStats.capped ? '#FF6B00' : '#00FFFF', color: nodeStats.capped ? '#FF6B00' : '#00FFFF' }}>
          {nodeStats.visible}/{nodeStats.total} nodes
          {nodeStats.capped && ' (capped)'}
        </div>
      )}

      {tooltip.show && (
        <div
          className="absolute z-50 px-2 py-1 text-xs text-white rounded pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            background: 'rgba(0, 0, 0, 0.8)',
            border: '1px solid #eab308',
            fontFamily: 'Orbitron, monospace',
            maxWidth: '280px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}
        >
          {tooltip.content}
        </div>
      )}

      <div className="absolute bottom-2 left-2 text-[8px] text-amber-400 font-mono">
        Orange = truncated (click to expand) | Drag to move
      </div>

      <div className="absolute bottom-2 right-2 flex gap-1">
        <button
          onClick={handleCollapseAll}
          className="w-7 h-7 flex items-center justify-center bg-[#1a1a1a] text-[#00FFFF] rounded border border-[#00FFFF] hover:bg-[#2a2a2a] transition-colors text-xs font-mono"
          title="Collapse All"
        >
          -
        </button>
        <button
          onClick={handleZoomIn}
          className="w-7 h-7 flex items-center justify-center bg-[#1a1a1a] text-[#00FFFF] rounded border border-[#00FFFF] hover:bg-[#2a2a2a] transition-colors text-xs font-mono"
          title="Zoom In"
        >
          +
        </button>
        <button
          onClick={handleZoomOut}
          className="w-7 h-7 flex items-center justify-center bg-[#1a1a1a] text-[#00FFFF] rounded border border-[#00FFFF] hover:bg-[#2a2a2a] transition-colors text-xs font-mono"
          title="Zoom Out"
        >
          -
        </button>
        <button
          onClick={handleFitToView}
          className="w-7 h-7 flex items-center justify-center bg-[#1a1a1a] text-[#00FFFF] rounded border border-[#00FFFF] hover:bg-[#2a2a2a] transition-colors text-xs font-mono"
          title="Fit to View"
        >
          &#9634;
        </button>
      </div>
    </div>
  );
};

export default ProjectTreeViz;
