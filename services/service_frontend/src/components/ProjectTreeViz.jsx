import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import socket from '../utils/socket';

const ProjectTreeViz = () => {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const [treeData, setTreeData] = useState(null);
  const [tooltip, setTooltip] = useState({ show: false, x: 0, y: 0, content: '' });
  const simulationRef = useRef(null);
  const zoomRef = useRef(null);

  useEffect(() => {
    fetch('/api/project-tree')
      .then(res => res.json())
      .then(data => {
        setTreeData(data);
      })
      .catch(err => console.error('Failed to fetch project tree:', err));

    socket.on('project_tree', (data) => {
      setTreeData(data);
    });

    return () => {
      socket.off('project_tree');
    };
  }, []);

  useEffect(() => {
    if (!treeData || !svgRef.current || !containerRef.current) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height);

    const zoomLayer = svg.append('g');
    const breatheLayer = zoomLayer.append('g');

    const g = breatheLayer;

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

    function convertToHierarchy(data) {
      if (!data.children) {
        return { ...data };
      }
      return {
        ...data,
        children: data.children.map(convertToHierarchy)
      };
    }

    const root = d3.hierarchy(convertToHierarchy(treeData));
    const links = root.links();
    const nodes = root.descendants();

    const simulation = d3.forceSimulation(nodes)
      .alphaDecay(0)
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

    const link = g.append('g')
      .attr('class', 'links')
      .selectAll('path')
      .data(links)
      .join('path')
      .attr('fill', 'none')
      .attr('stroke', '#00FFFF')
      .attr('stroke-opacity', 0.4)
      .attr('stroke-width', 2);

    const node = g.append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended));

    node.each(function(d) {
      const isFolder = d.data.children && d.data.children.length > 0;
      const group = d3.select(this);

      if (isFolder) {
        group.append('circle')
          .attr('r', 8)
          .attr('fill', '#00FFFF')
          .attr('stroke', '#00FFFF')
          .attr('stroke-width', 2)
          .style('filter', 'drop-shadow(0 0 4px #00FFFF)');
      } else {
        group.append('circle')
          .attr('r', 4)
          .attr('fill', '#FFD700')
          .attr('stroke', '#FFD700')
          .attr('stroke-width', 1)
          .style('filter', 'drop-shadow(0 0 3px #FFD700)');
      }
    });

    node.append('text')
      .text(d => d.data.name)
      .attr('x', 12)
      .attr('y', 4)
      .attr('fill', d => d.data.children && d.data.children.length > 0 ? '#888888' : '#555555')
      .attr('font-size', '9px')
      .attr('font-family', 'Orbitron, monospace')
      .style('pointer-events', 'none');

    node.on('mouseenter', (event, d) => {
      const rect = container.getBoundingClientRect();
      setTooltip({
        show: true,
        x: event.clientX - rect.left,
        y: event.clientY - rect.top - 40,
        content: `${d.data.path || d.data.name}${d.data.size ? ` (${formatSize(d.data.size)})` : ''}`
      });
    });

    node.on('mouseleave', () => {
      setTooltip({ show: false, x: 0, y: 0, content: '' });
    });

    node.on('click', (event, d) => {
      if (d.data.children && d.data.children.length > 0) {
        d._children = d.data.children;
        d.data.children = null;
      } else if (d._children) {
        d.data.children = d._children;
        d._children = null;
      }
      update();
    });

    function update() {
      const newNodes = root.descendants();
      const newLinks = root.links();

      const newNode = g.select('.nodes')
        .selectAll('g')
        .data(newNodes, d => d.data.name + Math.random());

      newNode.exit().remove();

      const nodeEnter = newNode.enter()
        .append('g')
        .attr('class', 'node')
        .call(d3.drag()
          .on('start', dragstarted)
          .on('drag', dragged)
          .on('end', dragended));

      nodeEnter.each(function(d) {
        const isFolder = d.data.children && d.data.children.length > 0;
        const group = d3.select(this);

        if (isFolder) {
          group.append('circle')
            .attr('r', 8)
            .attr('fill', '#00FFFF')
            .attr('stroke', '#00FFFF')
            .attr('stroke-width', 2)
            .style('filter', 'drop-shadow(0 0 4px #00FFFF)');
        } else {
          group.append('circle')
            .attr('r', 4)
            .attr('fill', '#FFD700')
            .attr('stroke', '#FFD700')
            .attr('stroke-width', 1)
            .style('filter', 'drop-shadow(0 0 3px #FFD700)');
        }
      });

      nodeEnter.append('text')
        .text(d => d.data.name)
        .attr('x', 12)
        .attr('y', 4)
        .attr('fill', d => d.data.children && d.data.children.length > 0 ? '#888888' : '#555555')
        .attr('font-size', '9px')
        .attr('font-family', 'Orbitron, monospace')
        .style('pointer-events', 'none');

      nodeEnter.on('mouseenter', (event, d) => {
        const rect = container.getBoundingClientRect();
        setTooltip({
          show: true,
          x: event.clientX - rect.left,
          y: event.clientY - rect.top - 40,
          content: `${d.data.path || d.data.name}${d.data.size ? ` (${formatSize(d.data.size)})` : ''}`
        });
      });

      nodeEnter.on('mouseleave', () => {
        setTooltip({ show: false, x: 0, y: 0, content: '' });
      });

      simulation.nodes(newNodes);
      simulation.force('link').links(newLinks);
      simulation.alpha(0.3).restart();
    }

    let time = 0;
    function tick() {
      time += 0.03;

      const breathScale = 1 + Math.sin(time * 0.5) * 0.10;
      g.attr('transform', `translate(${width / 2}, ${height / 2}) scale(${breathScale}) translate(${-width / 2}, ${-height / 2})`);

      link.attr('d', d => {
        const sx = d.source.x, sy = d.source.y;
        const tx = d.target.x, ty = d.target.y;
        const mx = (sx + tx) / 2, my = (sy + ty) / 2;
        return `M${sx},${sy}Q${mx},${my} ${tx},${ty}`;
      });

      node.attr('transform', d => {
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
  }, [treeData]);

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

  return (
    <div
      ref={containerRef}
      id="project-viz-panel"
      className="relative w-[500px] h-[600px] overflow-hidden rounded"
    >
      <svg ref={svgRef} className="w-full h-full bg-[#0a0a0a]" />

      {tooltip.show && (
        <div
          className="absolute z-50 px-2 py-1 text-xs text-white rounded pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            background: 'rgba(0, 0, 0, 0.8)',
            border: '1px solid #eab308',
            fontFamily: 'Orbitron, monospace',
            maxWidth: '250px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}
        >
          {tooltip.content}
        </div>
      )}

      <div className="absolute bottom-2 left-2 text-[8px] text-amber-400 font-mono">
        Click nodes to expand/collapse | Drag to move
      </div>

      <div className="absolute bottom-2 right-2 flex gap-1">
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
          ⊡
        </button>
      </div>
    </div>
  );
};

export default ProjectTreeViz;
