const STATUS_COLORS = {
  active: "#00d4ff",
  paused: "#4f8fff",
  blocked: "#ff2244",
  done: "#00ff88",
};

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
  const blockerCount = Array.isArray(project.blockers) ? project.blockers.length : 0;
  return 14 + Math.min(12, (taskCount * 2) + blockerCount + (degree * 1.5));
}

function nodeColor(project) {
  return STATUS_COLORS[String(project.status || "").toLowerCase()] || "#4f8fff";
}

function edgeColor(edge) {
  return EDGE_COLORS[String(edge.type || "").toLowerCase()] || "#4f8fff";
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
      detail.innerHTML = EMPTY_GRAPH_DETAIL;
      return;
    }

    if (selectedNode) {
      selectedNode = nodeIndex.get(selectedNode.name) || null;
    }

    if (!selectedNode) {
      selectedNode = nodes[0];
    }
    detail.innerHTML = detailMarkup(selectedNode);
  }

  function nodeByName(name) {
    return nodeIndex.get(name) || null;
  }

  function applyPhysics() {
    if (!nodes.length) return;
    const centerX = width / 2;
    const centerY = height / 2;

    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.hypot(dx, dy) || 1;
        const force = 1800 / (distance * distance);
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
      const target = 120;
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
    ctx.fillStyle = "rgba(0, 2, 15, 0.32)";
    ctx.fillRect(0, 0, width, height);

    for (const edge of edges) {
      const from = nodeByName(edge.from);
      const to = nodeByName(edge.to);
      if (!from || !to) continue;
      ctx.strokeStyle = edgeColor(edge);
      ctx.globalAlpha = 0.48;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    for (const node of nodes) {
      ctx.fillStyle = nodeColor(node);
      ctx.shadowColor = nodeColor(node);
      ctx.shadowBlur = hoverNode && hoverNode.name === node.name ? 18 : 10;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#e8f4ff";
      ctx.font = "11px SF Pro Display";
      ctx.textAlign = "center";
      ctx.fillText(node.name, node.x, node.y + node.radius + 16);
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
    hoverNode = hitTest(event.clientX, event.clientY);
    if (!hoverNode) {
      tooltip.classList.remove("is-visible");
      return;
    }
    tooltip.innerHTML = `
      <strong>${hoverNode.name}</strong>
      <span>${hoverNode.status || "paused"}</span>
      <div>${(hoverNode.next_tasks && hoverNode.next_tasks[0]) || "No next task logged yet."}</div>
    `;
    const rect = canvas.getBoundingClientRect();
    tooltip.style.left = `${event.clientX - rect.left + 12}px`;
    tooltip.style.top = `${event.clientY - rect.top + 12}px`;
    tooltip.classList.add("is-visible");
  });

  canvas.addEventListener("mouseleave", () => {
    hoverNode = null;
    tooltip.classList.remove("is-visible");
  });

  canvas.addEventListener("click", (event) => {
    const hit = hitTest(event.clientX, event.clientY);
    if (!hit) return;
    selectedNode = hit;
    detail.innerHTML = detailMarkup(selectedNode);
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
  detail.innerHTML = EMPTY_GRAPH_DETAIL;
  animate();

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
