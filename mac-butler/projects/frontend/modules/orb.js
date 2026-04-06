import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

const SPHERE_RADIUS = 160;
const ORB_VISUAL_EXTENT = 220;
const BASE_NODE_COUNT = 200;
const EXTRA_BRIGHT_COUNT = 0;
const EDGE_NEIGHBORS = 5;
const NETWORK_PARTICLE_COUNT = 120;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function easeInOutQuad(t) {
  return t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2;
}

function pseudoRandom(seed) {
  const x = Math.sin(seed * 127.1) * 43758.5453123;
  return x - Math.floor(x);
}

function fibonacciSphere(count, radius) {
  const points = [];
  const goldenRatio = (1 + Math.sqrt(5)) / 2;
  for (let index = 0; index < count; index += 1) {
    const theta = Math.acos(1 - (2 * (index + 0.5)) / count);
    const phi = (2 * Math.PI * index) / goldenRatio;
    const x = Math.sin(theta) * Math.cos(phi);
    const y = Math.cos(theta);
    const z = Math.sin(theta) * Math.sin(phi);
    points.push(new THREE.Vector3(x * radius, y * radius, z * radius));
  }
  return points;
}

function createGlowTexture(colorStops) {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  for (const stop of colorStops) {
    gradient.addColorStop(stop[0], stop[1]);
  }
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function createFloorTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createRadialGradient(256, 256, 0, 256, 256, 256);
  gradient.addColorStop(0, "rgba(0, 212, 255, 0.96)");
  gradient.addColorStop(0.24, "rgba(79, 143, 255, 0.46)");
  gradient.addColorStop(0.62, "rgba(0, 212, 255, 0.08)");
  gradient.addColorStop(1, "rgba(0, 2, 15, 0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 512, 512);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function createGradientBarGeometry() {
  const geometry = new THREE.PlaneGeometry(1.3, 1, 1, 1).toNonIndexed();
  const positions = geometry.attributes.position;
  const colors = [];
  for (let index = 0; index < positions.count; index += 1) {
    const y = positions.getY(index);
    if (y > 0) {
      colors.push(0 / 255, 212 / 255, 255 / 255);
    } else {
      colors.push(0 / 255, 68 / 255, 136 / 255);
    }
  }
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  return geometry;
}

class NeuralBackground {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.particles = [];
    this.lastFrame = performance.now();
    this.gridSize = 100;
    this._buildParticles();
    this._resize();
    window.addEventListener("resize", () => this._resize());
    this._tick = this._tick.bind(this);
    requestAnimationFrame(this._tick);
  }

  _buildParticles() {
    this.particles = Array.from({ length: NETWORK_PARTICLE_COUNT }, (_, index) => ({
      x: pseudoRandom(index + 1.2),
      y: pseudoRandom(index + 7.4),
      vx: (pseudoRandom(index + 17.9) - 0.5) * 0.000018,
      vy: (pseudoRandom(index + 23.7) - 0.5) * 0.000018,
      size: 1.5,
      color: "rgba(79, 143, 255, 0.6)",
    }));
  }

  _resize() {
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  _tick(now) {
    const delta = Math.min(32, now - this.lastFrame);
    this.lastFrame = now;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);
    const connectionCount = new Map();

    const grid = new Map();
    for (const particle of this.particles) {
      particle.x += particle.vx * delta;
      particle.y += particle.vy * delta;
      if (particle.x < 0) particle.x += 1;
      if (particle.x > 1) particle.x -= 1;
      if (particle.y < 0) particle.y += 1;
      if (particle.y > 1) particle.y -= 1;

      const px = particle.x * this.width;
      const py = particle.y * this.height;
      particle.px = px;
      particle.py = py;

      const gx = Math.floor(px / this.gridSize);
      const gy = Math.floor(py / this.gridSize);
      const key = `${gx}:${gy}`;
      if (!grid.has(key)) grid.set(key, []);
      grid.get(key).push(particle);
    }

    const neighborOffsets = [
      [0, 0], [1, 0], [0, 1], [1, 1], [-1, 1],
    ];

    ctx.lineWidth = 0.6;
    for (const [key, cellParticles] of grid.entries()) {
      const [gx, gy] = key.split(":").map(Number);
      for (const [ox, oy] of neighborOffsets) {
        const otherKey = `${gx + ox}:${gy + oy}`;
        const others = grid.get(otherKey);
        if (!others) continue;
        for (const a of cellParticles) {
          for (const b of others) {
            if (a === b) continue;
            if (otherKey === key && b.px <= a.px) continue;
            const dx = a.px - b.px;
            const dy = a.py - b.py;
            const distance = Math.sqrt(dx * dx + dy * dy);
            if (distance > 120) continue;
            const aCount = connectionCount.get(a) || 0;
            const bCount = connectionCount.get(b) || 0;
            if (aCount >= 5 || bCount >= 5) continue;
            connectionCount.set(a, aCount + 1);
            connectionCount.set(b, bCount + 1);
            const alpha = 0.12 * (1 - (distance / 120));
            ctx.strokeStyle = `rgba(79, 143, 255, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(a.px, a.py);
            ctx.lineTo(b.px, b.py);
            ctx.stroke();
          }
        }
      }
    }

    for (const particle of this.particles) {
      ctx.fillStyle = particle.color;
      ctx.beginPath();
      ctx.arc(particle.px, particle.py, particle.size, 0, Math.PI * 2);
      ctx.fill();
    }

    requestAnimationFrame(this._tick);
  }
}

class BurryOrb {
  constructor(canvas) {
    this.canvas = canvas;
    this.state = "idle";
    this.stateSince = performance.now();
    this.previousState = "idle";
    this.collapsePulse = null;
    this.lastRewireAt = 0;
    this.lastFrame = performance.now();
    this.micLevel = 0;
    this.simulatedSpeakingLevel = 0;
    this.currentPositions = [];
    this.edgePairs = [];
    this.nodeMeta = [];
    this.brightMeta = [];
    this.waveBars = [];
    this.rings = [];
    this.orbRadius = SPHERE_RADIUS;
    this.bootStartedAt = performance.now();
    this.idleSpinSpeed = 0;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(34, 1, 0.1, 2000);
    this.camera.position.set(0, 0, 350);
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    this.renderer.setClearColor(0x00020f, 0);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 1.4, 0.4, 0.3);
    bloomPass.threshold = 0.3;
    bloomPass.strength = 1.4;
    bloomPass.radius = 0.4;
    this.composer.addPass(bloomPass);

    this.root = new THREE.Group();
    this.root.position.set(0, 0, 0);
    this.scene.add(this.root);

    this.floor = this._createFloor();
    this.root.add(this.floor);

    this.nodeGroup = new THREE.Group();
    this.edgeGroup = new THREE.Group();
    this.ringGroup = new THREE.Group();
    this.centerGroup = new THREE.Group();
    this.root.add(this.edgeGroup);
    this.root.add(this.nodeGroup);
    this.root.add(this.ringGroup);
    this.root.add(this.centerGroup);

    this.smallTexture = createGlowTexture([
      [0, "rgba(0,170,255,0.92)"],
      [0.22, "rgba(0,170,255,0.8)"],
      [0.54, "rgba(0,212,255,0.28)"],
      [1, "rgba(0,0,0,0)"],
    ]);
    this.largeTexture = createGlowTexture([
      [0, "rgba(0,170,255,0.96)"],
      [0.18, "rgba(0,170,255,0.92)"],
      [0.42, "rgba(0,212,255,0.54)"],
      [0.76, "rgba(79,143,255,0.22)"],
      [1, "rgba(0,0,0,0)"],
    ]);

    this._createNodes();
    this._createEdges();
    this._createRings();
    this._createCenter();

    this._resize();
    window.addEventListener("resize", () => this._resize());
    this._animate = this._animate.bind(this);
    requestAnimationFrame(this._animate);
  }

  _createFloor() {
    const geometry = new THREE.PlaneGeometry(360, 220);
    const material = new THREE.MeshBasicMaterial({
      map: createFloorTexture(),
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const plane = new THREE.Mesh(geometry, material);
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = -222;
    return plane;
  }

  _createNodes() {
    const points = fibonacciSphere(BASE_NODE_COUNT, SPHERE_RADIUS);
    const tinyCount = Math.floor(BASE_NODE_COUNT * 0.60);
    const mediumCount = Math.floor(BASE_NODE_COUNT * 0.30);

    points.forEach((position, index) => {
      const direction = position.clone().normalize();
      const tangentA = new THREE.Vector3(0, 1, 0).cross(direction);
      if (tangentA.lengthSq() < 1e-5) tangentA.set(1, 0, 0).cross(direction);
      tangentA.normalize();
      const tangentB = direction.clone().cross(tangentA).normalize();

      let size = 1.8;
      let texture = this.smallTexture;
      if (index >= tinyCount && index < tinyCount + mediumCount) {
        size = 3.5;
      } else if (index >= tinyCount + mediumCount) {
        size = 7;
        texture = this.largeTexture;
      }

      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: texture,
        color: 0x00d4ff,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }));
      sprite.scale.set(size, size, size);
      sprite.position.copy(position);
      this.nodeGroup.add(sprite);

      this.nodeMeta.push({
        sprite,
        base: position.clone(),
        direction,
        tangentA,
        tangentB,
        size,
        phaseA: pseudoRandom(index + 13.7) * Math.PI * 2,
        phaseB: pseudoRandom(index + 33.2) * Math.PI * 2,
      });
      this.currentPositions.push(position.clone());
    });

    if (EXTRA_BRIGHT_COUNT > 0) {
      const selected = new Set();
      while (selected.size < EXTRA_BRIGHT_COUNT) {
        selected.add(Math.floor(pseudoRandom(selected.size + 91.4) * BASE_NODE_COUNT));
        selected.add(Math.floor(pseudoRandom(selected.size + 12.9) * BASE_NODE_COUNT));
        if (selected.size > EXTRA_BRIGHT_COUNT) break;
      }
      [...selected].slice(0, EXTRA_BRIGHT_COUNT).forEach((index, brightIndex) => {
        const meta = this.nodeMeta[index];
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
          map: this.largeTexture,
          color: 0x00d4ff,
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }));
        const size = 12;
        sprite.scale.set(size, size, size);
        sprite.position.copy(meta.base.clone().multiplyScalar(1.015));
        this.nodeGroup.add(sprite);
        this.brightMeta.push({ sprite, index, size, phase: pseudoRandom(brightIndex + 4.5) * Math.PI * 2 });
      });
    }
  }

  _buildEdgePairs(points, withPerturbation = false) {
    const pairs = new Map();
    for (let index = 0; index < points.length; index += 1) {
      const source = points[index];
      const distances = [];
      for (let other = 0; other < points.length; other += 1) {
        if (index === other) continue;
        const target = points[other];
        let distance = source.distanceTo(target);
        if (withPerturbation) distance *= lerp(0.88, 1.16, pseudoRandom(index * 97 + other * 13.1));
        distances.push([other, distance]);
      }
      distances.sort((a, b) => a[1] - b[1]);
      for (const [neighborIndex] of distances.slice(0, EDGE_NEIGHBORS)) {
        const a = Math.min(index, neighborIndex);
        const b = Math.max(index, neighborIndex);
        pairs.set(`${a}:${b}`, [a, b]);
      }
    }
    return [...pairs.values()];
  }

  _edgeGeometryFromPairs(pairs) {
    const positions = new Float32Array(pairs.length * 2 * 3);
    const colors = new Float32Array(pairs.length * 2 * 3);
    const edgeT = new Float32Array(pairs.length * 2);
    pairs.forEach(([aIndex, bIndex], edgeIndex) => {
      const a = this.currentPositions[aIndex];
      const b = this.currentPositions[bIndex];
      const offset = edgeIndex * 6;
      positions[offset + 0] = a.x;
      positions[offset + 1] = a.y;
      positions[offset + 2] = a.z;
      positions[offset + 3] = b.x;
      positions[offset + 4] = b.y;
      positions[offset + 5] = b.z;

      colors[offset + 0] = 0.04;
      colors[offset + 1] = 0.29;
      colors[offset + 2] = 1.0;
      colors[offset + 3] = 0.0;
      colors[offset + 4] = 0.83;
      colors[offset + 5] = 1.0;

      edgeT[edgeIndex * 2] = 0;
      edgeT[(edgeIndex * 2) + 1] = 1;
    });

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute("edgeT", new THREE.BufferAttribute(edgeT, 1));
    return geometry;
  }

  _createEdges() {
    this.edgePairs = this._buildEdgePairs(this.currentPositions, false);
    const geometry = this._edgeGeometryFromPairs(this.edgePairs);
    const material = new THREE.LineBasicMaterial({
      color: 0x1a5aff,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.edgeMaterial = material;
    this.edgeLines = new THREE.LineSegments(geometry, material);
    this.edgeGroup.add(this.edgeLines);
  }

  _createRings() {
    const configs = [
      { major: 185, minor: 148, tiltAxis: "x", tilt: 15, spinAxis: "y", speed: 0.0008, dashed: false },
      { major: 200, minor: 158, tiltAxis: "y", tilt: 55, spinAxis: "x", speed: 0.001, dashed: false },
      { major: 220, minor: 172, tiltAxis: "x", tilt: 75, spinAxis: "z", speed: 0.0012, dashed: true },
    ];

    configs.forEach((config, index) => {
      const curve = new THREE.EllipseCurve(0, 0, config.major, config.minor, 0, Math.PI * 2, false, 0);
      const points2D = curve.getPoints(240);
      const points = points2D.map((point) => new THREE.Vector3(point.x, 0, point.y));
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      let material;
      if (config.dashed) {
        material = new THREE.LineDashedMaterial({
          color: 0x00d4ff,
          transparent: true,
          opacity: 0.6,
          dashSize: 7,
          gapSize: 7,
        });
      } else {
        material = new THREE.LineBasicMaterial({
          color: 0x00d4ff,
          transparent: true,
          opacity: 0.6,
        });
      }
      const line = new THREE.LineLoop(geometry, material);
      if (config.dashed) line.computeLineDistances();
      const group = new THREE.Group();
      group.add(line);
      group.rotation[config.tiltAxis] = THREE.MathUtils.degToRad(config.tilt);
      this.ringGroup.add(group);
      this.rings.push({
        group,
        line,
        material,
        baseMajor: config.major,
        baseMinor: config.minor,
        spinAxis: config.spinAxis,
        speed: config.speed * (index === 0 ? 1 : 1.2),
      });
    });
  }

  _createCenter() {
    const torusMaterial = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0.92,
      blending: THREE.AdditiveBlending,
    });
    const torus = new THREE.Mesh(new THREE.TorusGeometry(60, 2.5, 16, 100), torusMaterial);
    this.centerGroup.add(torus);

    const halo = new THREE.Sprite(new THREE.SpriteMaterial({
      map: this.largeTexture,
      color: 0x00d4ff,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      opacity: 0.38,
    }));
    halo.scale.set(132, 132, 132);
    this.centerGroup.add(halo);

    const barGeometry = createGradientBarGeometry();
    const barMaterial = new THREE.MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.92,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    });

    for (let index = 0; index < 48; index += 1) {
      const mesh = new THREE.Mesh(barGeometry, barMaterial);
      mesh.position.x = lerp(-52, 52, index / 47);
      mesh.scale.y = 2;
      this.centerGroup.add(mesh);
      this.waveBars.push({ mesh, phase: pseudoRandom(index + 1.1) * Math.PI * 2 });
    }
  }

  _resize() {
    const width = Math.max(1, this.canvas.offsetWidth);
    const height = Math.max(1, this.canvas.offsetHeight);
    this.canvas.width = width;
    this.canvas.height = height;
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    this.renderer.setPixelRatio(pixelRatio);
    this.renderer.setSize(width, height, false);
    this.composer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.orbRadius = Math.min(width, height) * 0.36;
    this.root.scale.setScalar(this.orbRadius / ORB_VISUAL_EXTENT);
  }

  setMicLevel(level) {
    this.micLevel = clamp(level, 0, 1);
  }

  setState(nextState) {
    const cleaned = ["idle", "listening", "thinking", "executing", "speaking"].includes(nextState) ? nextState : "idle";
    if (cleaned === this.state) return;
    if (this.state === "thinking" && cleaned === "speaking") {
      this.collapsePulse = { start: performance.now(), duration: 800 };
    }
    this.previousState = this.state;
    this.state = cleaned;
    this.stateSince = performance.now();
  }

  _rebuildEdgesThinking(now) {
    if (now - this.lastRewireAt < 300) return;
    this.lastRewireAt = now;
    this.edgePairs = this._buildEdgePairs(this.currentPositions, true);
    this.edgeLines.geometry.dispose();
    this.edgeLines.geometry = this._edgeGeometryFromPairs(this.edgePairs);
  }

  _updateEdgePositions() {
    const positions = this.edgeLines.geometry.attributes.position.array;
    this.edgePairs.forEach(([aIndex, bIndex], edgeIndex) => {
      const a = this.currentPositions[aIndex];
      const b = this.currentPositions[bIndex];
      const offset = edgeIndex * 6;
      positions[offset + 0] = a.x;
      positions[offset + 1] = a.y;
      positions[offset + 2] = a.z;
      positions[offset + 3] = b.x;
      positions[offset + 4] = b.y;
      positions[offset + 5] = b.z;
    });
    this.edgeLines.geometry.attributes.position.needsUpdate = true;
  }

  _collapseRadiusFactor(now) {
    if (!this.collapsePulse) return 1;
    const elapsed = now - this.collapsePulse.start;
    const progress = clamp(elapsed / this.collapsePulse.duration, 0, 1);
    if (progress >= 1) {
      this.collapsePulse = null;
      return 1;
    }
    if (progress < 0.5) {
      return 1 - easeInOutQuad(progress * 2);
    }
    return easeInOutQuad((progress - 0.5) * 2);
  }

  _nodePosition(meta, _index, seconds, collapseFactor) {
    const mode = this.state;
    const direction = meta.direction;
    let radialScale = 1;
    let tangentOffset = 0;
    let tangentOffsetB = 0;
    let pulseScale = 1;

    if (mode === "idle") {
      pulseScale = 1 + (0.15 * ((Math.sin((seconds / 3) * Math.PI * 2 + meta.phaseA) + 1) / 2));
    } else if (mode === "listening") {
      pulseScale = 1 + (0.18 * ((Math.sin((seconds / 0.8) * Math.PI * 2 + meta.phaseA) + 1) / 2)) + (this.micLevel * 0.45);
      radialScale = 1 + (this.micLevel * 0.05);
    } else if (mode === "thinking") {
      const sway = Math.sin(seconds * 1.8 + meta.phaseA);
      const twist = Math.cos(seconds * 2.2 + meta.phaseB);
      radialScale = 1 + (0.06 * sway);
      tangentOffset = sway * 24;
      tangentOffsetB = twist * 22;
      pulseScale = 1 + (0.08 * ((Math.sin(seconds * 6 + meta.phaseA) + 1) / 2));
    } else if (mode === "executing") {
      radialScale = 1 + (0.015 * Math.sin(seconds * 3.6 + meta.phaseA));
      pulseScale = 1 + (0.12 * ((Math.sin(seconds * 7 + meta.phaseA) + 1) / 2));
    } else if (mode === "speaking") {
      pulseScale = 1 + (this.simulatedSpeakingLevel * 0.38);
      radialScale = 1 + (this.simulatedSpeakingLevel * 0.03);
    }

    const base = direction.clone().multiplyScalar(SPHERE_RADIUS * radialScale * collapseFactor);
    if (mode === "thinking") {
      base.addScaledVector(meta.tangentA, tangentOffset * collapseFactor);
      base.addScaledVector(meta.tangentB, tangentOffsetB * collapseFactor);
    }
    return { position: base, pulseScale };
  }

  _updateWaveform(seconds) {
    const energy = this.state === "listening"
      ? this.micLevel
      : this.state === "speaking"
        ? this.simulatedSpeakingLevel
        : this.state === "executing"
          ? 0.34 + (Math.sin(seconds * 12) * 0.06)
          : this.state === "thinking"
            ? 0.28 + (Math.sin(seconds * 8) * 0.12)
            : 0.08;
    this.waveBars.forEach((bar, index) => {
      const bin = Math.sin(seconds * 5.4 + bar.phase + (index * 0.21)) * 0.5 + 0.5;
      const height = this.state === "idle"
        ? 1.8 + (bin * 2.2)
        : 3 + ((bin * 17) * (0.32 + energy));
      bar.mesh.scale.y = height;
      bar.mesh.position.y = 0;
    });
  }

  _animate(now) {
    const delta = Math.min(32, now - this.lastFrame);
    this.lastFrame = now;
    const seconds = now * 0.001;
    const collapseFactor = this._collapseRadiusFactor(now);

    let rotationSpeed = this.state === "listening"
      ? 0.003
      : this.state === "executing"
        ? 0.0026
        : this.state === "thinking"
          ? 0.0022
          : this.state === "speaking"
            ? 0.0012
            : 0.0008;

    if (this.state === "idle") {
      const bootElapsed = now - this.bootStartedAt;
      if (bootElapsed < 1200) {
        rotationSpeed = 0;
      } else {
        this.idleSpinSpeed = Math.min(this.idleSpinSpeed + 0.00002, 0.0008);
        rotationSpeed = this.idleSpinSpeed;
      }
    }

    this.root.rotation.y += rotationSpeed * delta;
    this.root.rotation.x = 0;

    if (this.state === "speaking") {
      this.simulatedSpeakingLevel = 0.4 + ((Math.sin(seconds * 12) + 1) * 0.24);
    } else {
      this.simulatedSpeakingLevel *= 0.88;
    }

    this.nodeMeta.forEach((meta, index) => {
      const next = this._nodePosition(meta, index, seconds, collapseFactor);
      meta.sprite.position.copy(next.position);
      meta.sprite.scale.setScalar(meta.size * next.pulseScale);
      this.currentPositions[index].copy(next.position);
    });

    this.brightMeta.forEach((meta) => {
      const anchor = this.currentPositions[meta.index];
      const burst = 1 + 0.12 * ((Math.sin(seconds * 3.2 + meta.phase) + 1) / 2);
      meta.sprite.position.copy(anchor.clone().multiplyScalar(1.018));
      meta.sprite.scale.setScalar(meta.size * burst);
    });

    if (this.state === "thinking") {
      this._rebuildEdgesThinking(now);
    }

    this._updateEdgePositions();
    this.edgeMaterial.opacity = this.state === "speaking"
      ? 0.7
      : this.state === "executing"
        ? 0.78
        : this.state === "thinking"
          ? 0.48
          : this.state === "listening"
            ? 0.55
            : 0.4;
    this.edgeMaterial.color.set(
      this.state === "speaking"
        ? 0x6feaff
        : this.state === "executing"
          ? 0xffd37a
          : this.state === "thinking"
            ? 0x2e7eff
            : 0x1a5aff,
    );

    this.rings.forEach((ring, index) => {
      const baseSpeed = ring.speed * (
        this.state === "listening"
          ? 3
          : this.state === "executing"
            ? 2.6
            : this.state === "thinking"
              ? 2.2
              : this.state === "speaking"
                ? 1.4
                : 1
      );
      ring.group.rotation[ring.spinAxis] += baseSpeed * delta;
      const pulse = this.state === "thinking" ? (15 / ring.baseMajor) * Math.sin(seconds * 4 + index) : 0;
      ring.group.scale.setScalar(1 + pulse);
      ring.material.opacity = this.state === "speaking" ? 0.78 : this.state === "executing" ? 0.8 : this.state === "listening" ? 0.72 : 0.6;
      if (ring.material.color) {
        ring.material.color.set(
          this.state === "thinking"
            ? 0x4f8fff
            : this.state === "executing"
              ? 0xffc266
              : this.state === "speaking"
                ? 0x8af0ff
                : 0x00d4ff,
        );
      }
    });

    this.floor.material.opacity = this.state === "speaking" ? 0.62 : this.state === "executing" ? 0.58 : this.state === "listening" ? 0.54 : 0.48;
    this._updateWaveform(seconds);
    this.composer.render();
    requestAnimationFrame(this._animate);
  }
}

export function createOrbSystem({ networkCanvas, orbCanvas, enableBackground = false }) {
  return {
    background: enableBackground && networkCanvas ? new NeuralBackground(networkCanvas) : null,
    orb: new BurryOrb(orbCanvas),
  };
}
