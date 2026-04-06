function nodeColor(status) {
  const s = String(status || "").toLowerCase();
  if (s === "active") return { fill: "rgba(0,212,255,0.2)", stroke: "#00d4ff" };
  if (s === "paused") return { fill: "rgba(79,143,255,0.15)", stroke: "#4f8fff" };
  if (s === "blocked") return { fill: "rgba(255,34,68,0.15)", stroke: "#ff2244" };
  if (s === "done") return { fill: "rgba(0,255,136,0.15)", stroke: "#00ff88" };
  return { fill: "rgba(100,100,200,0.12)", stroke: "#6464c8" };
}

const EDGE_COLORS = {
  depends_on: "#4f8fff",
  blocked_by: "#ff2244",
  shares_resource: "#7b5ea7",
};

const EMPTY_GRAPH_DETAIL = `
  <div class="graph-detail-card">
    <strong>No project graph yet</strong>
    <span>Waiting for project and dependency data.</span>
    <div><em>Next</em> Add projects to the store or let the graph observer write edges.</div>
  </div>
`;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function nodeRadius(project, degree = 0) {
  const taskCount = Array.isArray(project.next_tasks) ? project.next_tasks.length : 0;
  return clamp(28 + taskCount * 2 + Math.floor(degree * 0.5), 28, 36);
}

function nodeStroke(project) {
  return nodeColor(project.status).stroke;
}

function nodeFill(project) {
  return nodeColor(project.status).fill;
}

function edgeColor(edge) {
  return EDGE_COLORS[String(edge.type || "").toLowerCase()] || EDGE_COLORS.depends_on;
}

function detailMarkup(project) {
  if (!project) return "";
  const nextTask = (project.next_tasks && project.next_tasks[0]) || "No next task logged yet.";
  const blocker = (project.blockers && project.blockers[0]) || "No blocker logged.";
  return `
    <div class="graph-detail-card">
      <strong>${project.name}</strong>
      <span>${project.status || "paused"} · ${Number(project.completion || 0)}%</span>
      <div><em>Next</em> ${nextTask}</div>
      <div><em>Blocker</em> ${blocker}</div>
    </div>
  `;
}

function normalizeProject(project) {
  const name = String(project?.name || "").trim();
  if (!name) return null;
  return {
    ...project,
    name,
    status: String(project?.status || "paused").trim().toLowerCase() || "paused",
    completion: Number(project?.completion || 0) || 0,
    next_tasks: Array.isArray(project?.next_tasks) ? project.next_tasks : [],
    blockers: Array.isArray(project?.blockers) ? project.blockers : [],
  };
}

function normalizeEdge(edge) {
  const from = String(edge?.from || "").trim();
  const to = String(edge?.to || "").trim();
  if (!from || !to) return null;
  return {
    ...edge,
    from,
    to,
    type: String(edge?.type || "").trim().toLowerCase() || "depends_on",
  };
}

function mergeProjectsWithEdges(projectItems, edgeItems) {
  const merged = new Map();

  for (const project of Array.isArray(projectItems) ? projectItems : []) {
    const normalized = normalizeProject(project);
    if (!normalized) continue;
    merged.set(normalized.name, normalized);
  }

  for (const edge of Array.isArray(edgeItems) ? edgeItems : []) {
    const normalized = normalizeEdge(edge);
    if (!normalized) continue;
    for (const name of [normalized.from, normalized.to]) {
      if (merged.has(name)) continue;
      merged.set(name, {
        name,
        status: "paused",
        completion: 0,
        description: "Observed from the project relationship graph.",
        next_tasks: [],
        blockers: [],
      });
    }
  }

  return [...merged.values()];
}

export function createProjectGraph({ canvas, tooltip, detail }) {
  const ctx = canvas.getContext("2d");
  let projects = [];
  let edges = [];
  let nodes = [];
  let nodeIndex = new Map();
  let hoverNode = null;
  let selectedNode = null;
  let rafId = 0;
  let width = 0;
  let height = 0;
  let mouseX = 0;
  let mouseY = 0;

function ensureSize() {
    const nextWidth = Math.max(1, canvas.clientWidth || canvas.offsetWidth || 1);
    const nextHeight = Math.max(1, canvas.clientHeight || canvas.offsetHeight || 1);
    if (nextWidth === width && nextHeight === height) return;
    width = nextWidth;
    height = nextHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function rebuildNodes() {
    const priorNodes = new Map(nodes.map((node) => [node.name, node]));
    const graphProjects = mergeProjectsWithEdges(projects, edges);
    const edgeCounts = new Map();
    for (const edge of edges) {
      const normalized = normalizeEdge(edge);
      if (!normalized) continue;
      edgeCounts.set(normalized.from, (edgeCounts.get(normalized.from) || 0) + 1);
      edgeCounts.set(normalized.to, (edgeCounts.get(normalized.to) || 0) + 1);
    }
    const radius = Math.min(width, height) * 0.28 || 120;
    const centerX = width / 2;
    const centerY = height / 2;
    nodes = graphProjects.map((project, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, graphProjects.length);
      const previous = priorNodes.get(project.name);
      const degree = edgeCounts.get(project.name) || 0;
      return {
        ...project,
        x: previous?.x ?? (centerX + Math.cos(angle) * radius),
        y: previous?.y ?? (centerY + Math.sin(angle) * radius),
        vx: previous?.vx ?? 0,
        vy: previous?.vy ?? 0,
        radius: nodeRadius(project, degree),
      };
    });
    nodeIndex = new Map(nodes.map((node) => [node.name, node]));

    if (!nodes.length) {
      selectedNode = null;
      detail.innerHTML = "";
      detail.classList.remove("is-visible");
      return;
    }

    if (selectedNode) {
      selectedNode = nodeIndex.get(selectedNode.name) || null;
      if (selectedNode) {
        detail.innerHTML = detailMarkup(selectedNode);
        detail.classList.add("is-visible");
      } else {
        detail.innerHTML = "";
        detail.classList.remove("is-visible");
      }
    }
  }

  function nodeByName(name) {
    return nodeIndex.get(name) || null;
  }

  function applyPhysics() {
    if (!nodes.length) return;

    // No edges: animate toward horizontal row (or vertical on narrow canvas)
    if (!edges.length) {
      const isNarrow = height > width * 1.2;
      nodes.forEach((node, index) => {
        const targetX = isNarrow
          ? width / 2
          : (width / (nodes.length + 1)) * (index + 1);
        const targetY = isNarrow
          ? (height / (nodes.length + 1)) * (index + 1)
          : height / 2;
        node.vx += (targetX - node.x) * 0.06;
        node.vy += (targetY - node.y) * 0.06;
        node.vx *= 0.78;
        node.vy *= 0.78;
        node.x = clamp(node.x + node.vx, node.radius + 8, width - node.radius - 8);
        node.y = clamp(node.y + node.vy, node.radius + 8, height - node.radius - 8);
      });
      return;
    }

    const centerX = width / 2;
    const centerY = height / 2;

    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.hypot(dx, dy) || 1;
        const force = 9000 / (distance * distance);
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }

    for (const edge of edges) {
      const from = nodeByName(edge.from);
      const to = nodeByName(edge.to);
      if (!from || !to) continue;
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const distance = Math.hypot(dx, dy) || 1;
      const target = 130;
      const spring = (distance - target) * 0.002;
      const fx = (dx / distance) * spring;
      const fy = (dy / distance) * spring;
      from.vx += fx;
      from.vy += fy;
      to.vx -= fx;
      to.vy -= fy;
    }

    for (const node of nodes) {
      node.vx += (centerX - node.x) * 0.0006;
      node.vy += (centerY - node.y) * 0.0006;
      node.vx *= 0.92;
      node.vy *= 0.92;
      node.x = clamp(node.x + node.vx, node.radius + 8, width - node.radius - 8);
      node.y = clamp(node.y + node.vy, node.radius + 8, height - node.radius - 8);
    }
  }

  function draw() {
    ensureSize();
    ctx.clearRect(0, 0, width, height);

    // Draw edges with arrowheads
    for (let edgeIndex = 0; edgeIndex < edges.length; edgeIndex += 1) {
      const edge = edges[edgeIndex];
      const from = nodeByName(edge.from);
      const to = nodeByName(edge.to);
      if (!from || !to) continue;

      const color = edgeColor(edge);
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 2) continue;

      const nx = dx / dist;
      const ny = dy / dist;
      const arrowSize = 9;
      const startX = from.x + nx * from.radius;
      const startY = from.y + ny * from.radius;
      const endX = to.x - nx * (to.radius + arrowSize);
      const endY = to.y - ny * (to.radius + arrowSize);

      const edgeOpacity = Math.sin(Date.now() / 1200 + edgeIndex) * 0.15 + 0.45;
      const isDependsOn = String(edge.type || "").toLowerCase() === "depends_on";

      // Line
      ctx.globalAlpha = edgeOpacity;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      if (isDependsOn) {
        ctx.setLineDash([6, 4]);
        ctx.lineDashOffset = -(Date.now() / 80) % 10;
      } else {
        ctx.setLineDash([]);
      }
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(endX, endY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Arrowhead
      const angle = Math.atan2(dy, dx);
      ctx.globalAlpha = edgeOpacity + 0.2;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(endX + nx * arrowSize, endY + ny * arrowSize);
      ctx.lineTo(
        endX - arrowSize * Math.cos(angle - Math.PI / 5),
        endY - arrowSize * Math.sin(angle - Math.PI / 5),
      );
      ctx.lineTo(
        endX - arrowSize * Math.cos(angle + Math.PI / 5),
        endY - arrowSize * Math.sin(angle + Math.PI / 5),
      );
      ctx.closePath();
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    // Draw nodes
    for (const node of nodes) {
      const stroke = nodeStroke(node);
      const fill = nodeFill(node);
      const isHover = hoverNode && hoverNode.name === node.name;

      // Glow shadow
      ctx.shadowColor = stroke;
      ctx.shadowBlur = isHover ? 26 : 14;

      // Fill circle
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();

      ctx.shadowBlur = 0;

      // Border
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.stroke();

      // Label: inside node if near bottom edge, otherwise below
      const label = node.name.length > 14 ? node.name.slice(0, 13) + "\u2026" : node.name;
      ctx.font = "11px SF Mono, monospace";
      ctx.fillStyle = "rgba(232,244,255,0.85)";
      ctx.textAlign = "center";
      const labelY = node.y + node.radius + 14;
      if (labelY + 12 > height) {
        // Draw label inside the node when it would clip
        ctx.textBaseline = "middle";
        ctx.fillText(label, node.x, node.y);
      } else {
        ctx.textBaseline = "top";
        ctx.fillText(label, node.x, labelY);
      }
      ctx.textBaseline = "alphabetic";
    }
  }

  function animate() {
    applyPhysics();
    draw();
    rafId = window.requestAnimationFrame(animate);
  }

  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    return nodes.find((node) => Math.hypot(node.x - x, node.y - y) <= node.radius + 6) || null;
  }

  canvas.addEventListener("mousemove", (event) => {
    const rect = canvas.getBoundingClientRect();
    mouseX = event.clientX - rect.left;
    mouseY = event.clientY - rect.top;
    hoverNode = hitTest(event.clientX, event.clientY);
    if (!hoverNode) {
      tooltip.classList.remove("is-visible");
    } else {
      const completion = Number(hoverNode.completion || 0);
      const nextTask = (hoverNode.next_tasks && hoverNode.next_tasks[0]) || "No next task logged yet.";
      tooltip.innerHTML = `
        <strong>${hoverNode.name}</strong>
        <span>${hoverNode.status || "paused"} · ${completion}%</span>
        <div>${nextTask}</div>
      `;
      const tipW = tooltip.offsetWidth || 200;
      const tipH = tooltip.offsetHeight || 80;
      let tipLeft = mouseX + 14;
      let tipTop = mouseY + 14;
      if (tipLeft + tipW > rect.width) tipLeft = mouseX - tipW - 8;
      if (tipTop + tipH > rect.height) tipTop = mouseY - tipH - 8;
      if (tipLeft < 0) tipLeft = 8;
      if (tipTop < 0) tipTop = 8;
      tooltip.style.left = `${tipLeft}px`;
      tooltip.style.top = `${tipTop}px`;
      tooltip.classList.add("is-visible");
    }
  });

  canvas.addEventListener("mouseleave", () => {
    hoverNode = null;
    tooltip.classList.remove("is-visible");
  });

  canvas.addEventListener("click", (event) => {
    const hit = hitTest(event.clientX, event.clientY);
    if (!hit) {
      // Dismiss detail card when clicking empty canvas space
      selectedNode = null;
      detail.innerHTML = "";
      detail.classList.remove("is-visible");
      return;
    }
    selectedNode = hit;
    detail.innerHTML = detailMarkup(selectedNode);
    detail.classList.add("is-visible");
  });

  async function refresh() {
    let nextProjects = projects;
    let nextEdges = edges;

    try {
      const [projectsResponse, graphResponse] = await Promise.all([
        fetch("/api/projects"),
        fetch("/api/graph"),
      ]);

      if (projectsResponse.ok) {
        const payload = await projectsResponse.json();
        nextProjects = Array.isArray(payload) ? payload : nextProjects;
      }
      if (graphResponse.ok) {
        const payload = await graphResponse.json();
        nextEdges = Array.isArray(payload.edges) ? payload.edges : [];
      }
    } catch (error) {
      console.error(error);
    }

    projects = Array.isArray(nextProjects) ? nextProjects : [];
    edges = Array.isArray(nextEdges) ? nextEdges.map((edge) => normalizeEdge(edge)).filter(Boolean) : [];
    rebuildNodes();
  }

  function setProjects(nextProjects) {
    projects = Array.isArray(nextProjects) ? nextProjects.map((project) => normalizeProject(project)).filter(Boolean) : [];
    rebuildNodes();
  }

  ensureSize();
  detail.innerHTML = "";
  animate();

  if (canvas.parentElement && typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => ensureSize()).observe(canvas.parentElement);
  }

  return {
    destroy() {
      if (rafId) {
        window.cancelAnimationFrame(rafId);
      }
    },
    refresh,
    setProjects,
  };
}
