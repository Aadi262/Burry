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

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function nodeRadius(project) {
  const taskCount = Array.isArray(project.next_tasks) ? project.next_tasks.length : 0;
  return 14 + Math.min(10, taskCount * 2);
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

export function createProjectGraph({ canvas, tooltip, detail }) {
  const ctx = canvas.getContext("2d");
  let projects = [];
  let edges = [];
  let nodes = [];
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
    const radius = Math.min(width, height) * 0.28 || 120;
    const centerX = width / 2;
    const centerY = height / 2;
    nodes = projects.map((project, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, projects.length);
      return {
        ...project,
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        radius: nodeRadius(project),
      };
    });
    if (!selectedNode && nodes[0]) {
      selectedNode = nodes[0];
      detail.innerHTML = detailMarkup(selectedNode);
    }
  }

  function nodeByName(name) {
    return nodes.find((node) => node.name === name) || null;
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
    try {
      const response = await fetch("/api/graph");
      if (!response.ok) return;
      const payload = await response.json();
      edges = Array.isArray(payload.edges) ? payload.edges : [];
    } catch (error) {
      console.error(error);
      edges = [];
    }
  }

  function setProjects(nextProjects) {
    projects = Array.isArray(nextProjects) ? nextProjects : [];
    ensureSize();
    rebuildNodes();
  }

  ensureSize();
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
