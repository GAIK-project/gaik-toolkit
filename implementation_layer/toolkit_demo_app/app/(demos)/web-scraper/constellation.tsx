"use client";

// The crawl as a constellation: each page a glowing node, its undiscovered links dim
// stars orbiting it. When the crawler requests one of those links, its star grows
// into a node; edges draw from the page that linked it. While the extractor reads,
// a wave runs over the pages, and pages that hold cited values keep an amber halo.
//
// A direct Three.js island (no React renderer): nodes arrive from a stream and the
// layout is a small force simulation, which is simplest to drive imperatively.

import { cn } from "@/lib/utils";
import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { CrawlNode, NodeStatus, Phase } from "./scraper-data";

export interface ConstellationProps {
  nodes: CrawlNode[];
  phase: Phase;
  /** Cited values per page, by final URL. */
  citations: Record<string, number>;
  selected: string | null;
  onSelect: (url: string | null) => void;
  className?: string;
}

const PALETTE = {
  start: new THREE.Color("#f7c96b"),
  depth: [
    new THREE.Color("#5eead4"),
    new THREE.Color("#67e8f9"),
    new THREE.Color("#a5b4fc"),
  ],
  fetching: new THREE.Color("#e2f8f4"),
  skipped: new THREE.Color("#fb7185"),
  frontier: new THREE.Color("#a9bdd6"),
  cited: new THREE.Color("#fbbf24"),
  selected: new THREE.Color("#ffffff"),
};
const MAX_FRONTIER = 260;
const MAX_EDGES = 64;
const FRONTIER_PER_PAGE = 22;

interface Frontier {
  url: string;
  offset: THREE.Vector3;
}

interface Body {
  id: string;
  finalUrl: string;
  parent: string | null;
  depth: number;
  order: number;
  status: NodeStatus;
  title: string;
  words: number;
  pos: THREE.Vector3;
  vel: THREE.Vector3;
  born: number;
  settledAt: number;
  core: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>;
  glow: THREE.Sprite;
  ring: THREE.Sprite;
  halo: THREE.Sprite;
  pulse: THREE.Sprite;
  frontier: Frontier[];
  spin: number;
}

function easeOutBack(t: number): number {
  const c = 1.6;
  return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

function glowTexture(): THREE.CanvasTexture {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(
    size / 2,
    size / 2,
    0,
    size / 2,
    size / 2,
    size / 2,
  );
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.18, "rgba(255,255,255,0.55)");
  gradient.addColorStop(0.45, "rgba(255,255,255,0.12)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function ringTexture(): THREE.CanvasTexture {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.strokeStyle = "rgba(255,255,255,0.95)";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 6, 0, Math.PI * 2);
  ctx.stroke();
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** Evenly spread directions on a sphere (Fibonacci lattice). */
function directions(count: number, seed: number): THREE.Vector3[] {
  const result: THREE.Vector3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - ((i + 0.5) / count) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i + seed;
    result.push(
      new THREE.Vector3(Math.cos(theta) * r, y * 0.7, Math.sin(theta) * r),
    );
  }
  return result;
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++)
    h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10000) / 10000;
}

class CrawlScene {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(42, 1, 0.1, 200);
  private controls: OrbitControls;
  private bodies = new Map<string, Body>();
  private sphere = new THREE.SphereGeometry(1, 24, 16);
  private glowMap = glowTexture();
  private ringMap = ringTexture();
  private frontierPoints: THREE.Points;
  private frontierPositions = new Float32Array(MAX_FRONTIER * 3);
  private edgeLines: THREE.LineSegments;
  private edgePositions = new Float32Array(MAX_EDGES * 6);
  private edgeColors = new Float32Array(MAX_EDGES * 6);
  private edgeBorn = new Map<string, number>();
  private labels = new Map<string, HTMLDivElement>();
  private clock = new THREE.Clock();
  private frame = 0;
  private visible = true;
  private center = new THREE.Vector3();
  private pointer: { x: number; y: number } | null = null;
  private down: { x: number; y: number } | null = null;
  private hovered: string | null = null;
  private phase: Phase = "idle";
  private citations: Record<string, number> = {};
  private selected: string | null = null;
  private observer: IntersectionObserver;
  private resizer: ResizeObserver;
  readonly reducedMotion: boolean;
  rotating: boolean;
  onSelect: (url: string | null) => void = () => {};
  onRotatingChange: (on: boolean) => void = () => {};

  constructor(
    private host: HTMLDivElement,
    private overlay: HTMLDivElement,
  ) {
    this.reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    this.rotating = !this.reducedMotion;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(this.renderer.domElement);
    this.renderer.domElement.className = "block h-full w-full touch-pan-y";

    this.camera.position.set(0, 2.2, 8.5);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableZoom = false; // the page keeps the wheel
    this.controls.enablePan = false;
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.rotateSpeed = 0.6;
    this.controls.autoRotate = this.rotating;
    this.controls.autoRotateSpeed = 0.55;

    const frontierGeometry = new THREE.BufferGeometry();
    frontierGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(this.frontierPositions, 3).setUsage(
        THREE.DynamicDrawUsage,
      ),
    );
    frontierGeometry.setDrawRange(0, 0);
    this.frontierPoints = new THREE.Points(
      frontierGeometry,
      new THREE.PointsMaterial({
        color: PALETTE.frontier,
        size: 0.16,
        map: this.glowMap,
        transparent: true,
        opacity: 0.9,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    this.frontierPoints.frustumCulled = false;
    this.scene.add(this.frontierPoints);

    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(this.edgePositions, 3).setUsage(
        THREE.DynamicDrawUsage,
      ),
    );
    edgeGeometry.setAttribute(
      "color",
      new THREE.BufferAttribute(this.edgeColors, 3).setUsage(
        THREE.DynamicDrawUsage,
      ),
    );
    edgeGeometry.setDrawRange(0, 0);
    this.edgeLines = new THREE.LineSegments(
      edgeGeometry,
      new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.7,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    this.edgeLines.frustumCulled = false;
    this.scene.add(this.edgeLines);

    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointermove", this.handleMove);
    canvas.addEventListener("pointerleave", this.handleLeave);
    canvas.addEventListener("pointerdown", this.handleDown);
    canvas.addEventListener("pointerup", this.handleUp);
    this.controls.addEventListener("start", this.handleDragStart);

    this.resizer = new ResizeObserver(() => this.resize());
    this.resizer.observe(host);
    this.observer = new IntersectionObserver(([entry]) => {
      this.visible = entry.isIntersecting;
    });
    this.observer.observe(host);
    this.resize();
    this.frame = requestAnimationFrame(this.tick);
  }

  setRotating(on: boolean) {
    this.rotating = on;
    this.controls.autoRotate = on;
    this.onRotatingChange(on);
  }

  sync(
    nodes: CrawlNode[],
    phase: Phase,
    citations: Record<string, number>,
    selected: string | null,
  ) {
    const now = this.clock.getElapsedTime();
    this.phase = phase;
    this.citations = citations;
    this.selected = selected;
    const ids = new Set(nodes.map((node) => node.url));
    for (const [id, body] of this.bodies) if (!ids.has(id)) this.remove(body);

    for (const node of nodes) {
      let body = this.bodies.get(node.url);
      if (!body) body = this.add(node, now);
      const statusChanged = body.status !== node.status;
      body.finalUrl = node.finalUrl;
      body.title = node.title || node.finalUrl.replace(/^https?:\/\//, "");
      body.words = node.words ?? 0;
      if (statusChanged) {
        body.status = node.status;
        body.settledAt = now;
        if (node.status === "page")
          body.frontier = this.frontierFor(body, node.links ?? []);
      }
    }
    // A link that became a node is no longer a frontier star.
    for (const body of this.bodies.values())
      body.frontier = body.frontier.filter((f) => !this.lookup(f.url));
  }

  private lookup(url: string | null): Body | undefined {
    if (!url) return undefined;
    const direct = this.bodies.get(url);
    if (direct) return direct;
    for (const body of this.bodies.values())
      if (body.finalUrl === url) return body;
    return undefined;
  }

  private sprite(
    color: THREE.Color,
    map: THREE.Texture,
    opacity: number,
  ): THREE.Sprite {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map,
        color,
        transparent: true,
        opacity,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    this.scene.add(sprite);
    return sprite;
  }

  private add(node: CrawlNode, now: number): Body {
    const parent = this.lookup(node.parent);
    const pos = new THREE.Vector3();
    const star = parent?.frontier.find(
      (f) => f.url === node.url || f.url === node.finalUrl,
    );
    if (parent && star) {
      pos.copy(this.frontierWorld(parent, star, now));
    } else if (parent) {
      const h = hash(node.url);
      pos
        .copy(parent.pos)
        .add(
          new THREE.Vector3(
            Math.cos(h * 6.28),
            (h - 0.5) * 0.6,
            Math.sin(h * 6.28),
          ).multiplyScalar(0.6),
        );
    }
    const color =
      node.depth === 0
        ? PALETTE.start
        : PALETTE.depth[Math.min(node.depth - 1, 2)];
    const core = new THREE.Mesh(
      this.sphere,
      new THREE.MeshBasicMaterial({ color: color.clone() }),
    );
    this.scene.add(core);
    const body: Body = {
      id: node.url,
      finalUrl: node.finalUrl,
      parent: node.parent,
      depth: node.depth,
      order: node.order,
      status: node.status,
      title: node.title || node.url,
      words: node.words ?? 0,
      pos,
      vel: new THREE.Vector3(),
      born: this.reducedMotion ? now - 10 : now,
      settledAt: this.reducedMotion ? now - 10 : now,
      core,
      glow: this.sprite(color.clone(), this.glowMap, 0.7),
      ring: this.sprite(PALETTE.fetching.clone(), this.ringMap, 0),
      halo: this.sprite(PALETTE.cited.clone(), this.ringMap, 0),
      pulse: this.sprite(PALETTE.fetching.clone(), this.glowMap, 0),
      frontier: [],
      spin: hash(node.url) * Math.PI * 2,
    };
    this.bodies.set(node.url, body);
    if (node.status === "page")
      body.frontier = this.frontierFor(body, node.links ?? []);
    this.edgeBorn.set(node.url, body.born);
    return body;
  }

  private remove(body: Body) {
    for (const object of [
      body.core,
      body.glow,
      body.ring,
      body.halo,
      body.pulse,
    ]) {
      this.scene.remove(object);
      (object.material as THREE.Material).dispose();
    }
    this.labels.get(body.id)?.remove();
    this.labels.delete(body.id);
    this.edgeBorn.delete(body.id);
    this.bodies.delete(body.id);
  }

  private frontierFor(body: Body, links: string[]): Frontier[] {
    const pages = Math.max(
      1,
      [...this.bodies.values()].filter((b) => b.status === "page").length,
    );
    const limit = Math.min(FRONTIER_PER_PAGE, Math.floor(MAX_FRONTIER / pages));
    const fresh = links.filter((url) => !this.lookup(url)).slice(0, limit);
    const dirs = directions(fresh.length, body.spin);
    return fresh.map((url, i) => ({
      url,
      offset: dirs[i].multiplyScalar(0.75 + hash(url) * 0.55),
    }));
  }

  private frontierWorld(
    body: Body,
    star: Frontier,
    time: number,
  ): THREE.Vector3 {
    const angle = this.reducedMotion ? body.spin : body.spin + time * 0.18;
    const { x, y, z } = star.offset;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    return new THREE.Vector3(x * cos - z * sin, y, x * sin + z * cos).add(
      body.pos,
    );
  }

  private simulate(dt: number) {
    const list = [...this.bodies.values()];
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const d = new THREE.Vector3().subVectors(list[i].pos, list[j].pos);
        let dist2 = d.lengthSq();
        if (dist2 < 1e-4) {
          d.set(hash(list[i].id) - 0.5, hash(list[j].id) - 0.5, 0.1);
          dist2 = d.lengthSq();
        }
        const force = 1.6 / (Math.max(dist2, 0.09) * Math.sqrt(dist2));
        d.multiplyScalar(force * dt);
        list[i].vel.add(d);
        list[j].vel.sub(d);
      }
    }
    for (const body of list) {
      const parent = this.lookup(body.parent);
      if (parent && parent !== body) {
        const d = new THREE.Vector3().subVectors(body.pos, parent.pos);
        const length = Math.max(d.length(), 1e-3);
        const rest =
          body.status === "skipped" ? 1.1 : body.depth > 1 ? 1.5 : 2.0;
        d.multiplyScalar(((length - rest) / length) * 3.2 * dt);
        body.vel.sub(d);
        parent.vel.add(d.multiplyScalar(0.25));
      }
      const pull = body.depth === 0 ? 2.5 : 0.08;
      body.vel.addScaledVector(body.pos, -pull * dt);
      body.vel.multiplyScalar(Math.exp(-3.4 * dt));
      body.pos.addScaledVector(body.vel, dt);
    }
  }

  private tick = () => {
    this.frame = requestAnimationFrame(this.tick);
    const dt = Math.min(this.clock.getDelta(), 1 / 30);
    if (!this.visible || document.hidden) return;
    const now = this.clock.getElapsedTime();
    // Reduced motion: let the layout settle at once instead of drifting into place.
    const steps = this.reducedMotion ? 8 : 1;
    for (let i = 0; i < steps; i++)
      this.simulate(dt * (this.reducedMotion ? 2 : 1));
    this.update(now);
    this.frameCamera(dt);
    this.controls.update(dt);
    this.renderer.render(this.scene, this.camera);
    this.placeLabels();
  };

  private update(now: number) {
    const reading = this.phase === "schema" || this.phase === "extracting";
    const motion = this.reducedMotion ? 0 : 1;
    let star = 0;
    let edge = 0;
    for (const body of this.bodies.values()) {
      const age = now - body.born;
      const appear = this.reducedMotion
        ? 1
        : easeOutBack(Math.min(1, age / 0.7));
      const settle = Math.min(1, (now - body.settledAt) / 0.6);
      let radius = 0.06;
      let glowScale = 0.8;
      let glowOpacity = 0.55;
      const base =
        body.depth === 0
          ? PALETTE.start
          : PALETTE.depth[Math.min(Math.max(body.depth - 1, 0), 2)];
      let color = base;
      if (body.status === "fetching") {
        glowOpacity = 0.45 + 0.25 * Math.sin(now * 7) * motion;
        color = PALETTE.fetching;
      } else if (body.status === "page") {
        radius = 0.085 + Math.min(0.13, Math.sqrt(body.words) / 190);
        const bloom = this.reducedMotion ? 0 : (1 - easeOutCubic(settle)) * 0.9;
        glowScale = radius * 11 * (1 + bloom);
        glowOpacity = 0.72;
        if (reading)
          glowOpacity =
            0.45 +
            0.4 * Math.max(0, Math.sin(now * 3.2 - body.order * 0.8)) * motion +
            (1 - motion) * 0.3;
      } else {
        color = PALETTE.skipped;
        radius = 0.045;
        glowScale = 0.55;
        glowOpacity = 0.3;
      }
      body.core.material.color.lerp(color, 0.12);
      body.core.position.copy(body.pos);
      body.core.scale.setScalar(radius * appear);
      body.glow.position.copy(body.pos);
      body.glow.scale.setScalar(glowScale * appear);
      (body.glow.material as THREE.SpriteMaterial).color.lerp(color, 0.12);
      (body.glow.material as THREE.SpriteMaterial).opacity = glowOpacity;

      // Fetching: a ring that keeps expanding from the node, and a spark that travels
      // the edge from the linking page.
      const ringMaterial = body.ring.material as THREE.SpriteMaterial;
      const selected = this.selected === body.id;
      body.ring.position.copy(body.pos);
      if (body.status === "fetching" && motion) {
        const wave = (now * 1.3 + body.spin) % 1;
        body.ring.scale.setScalar(0.25 + wave * 0.75);
        ringMaterial.opacity = 0.8 * (1 - wave);
        ringMaterial.color.copy(PALETTE.fetching);
      } else if (selected || this.hovered === body.id) {
        body.ring.scale.setScalar(Math.max(0.5, radius * 6));
        ringMaterial.opacity = selected ? 0.95 : 0.5;
        ringMaterial.color.copy(PALETTE.selected);
      } else {
        ringMaterial.opacity = 0;
      }

      const cited = this.citations[body.finalUrl] ?? 0;
      const haloMaterial = body.halo.material as THREE.SpriteMaterial;
      body.halo.position.copy(body.pos);
      haloMaterial.opacity +=
        ((cited ? 0.85 : 0) - haloMaterial.opacity) * 0.08;
      body.halo.scale.setScalar(
        Math.max(0.42, radius * 4.4) +
          Math.sin(now * 2 + body.spin) * 0.03 * motion,
      );

      const parent = this.lookup(body.parent);
      const pulseMaterial = body.pulse.material as THREE.SpriteMaterial;
      if (parent && body.status === "fetching" && motion) {
        const t = (now * 1.6 + body.spin) % 1;
        body.pulse.position.lerpVectors(parent.pos, body.pos, easeOutCubic(t));
        body.pulse.scale.setScalar(0.35);
        pulseMaterial.opacity = 0.9;
      } else {
        pulseMaterial.opacity = 0;
      }

      if (parent && edge < MAX_EDGES) {
        const grow = this.reducedMotion
          ? 1
          : easeOutCubic(
              Math.min(1, (now - (this.edgeBorn.get(body.id) ?? now)) / 0.55),
            );
        const end = new THREE.Vector3().lerpVectors(parent.pos, body.pos, grow);
        this.edgePositions.set(
          [parent.pos.x, parent.pos.y, parent.pos.z, end.x, end.y, end.z],
          edge * 6,
        );
        const tint =
          body.status === "skipped" ? PALETTE.skipped : PALETTE.depth[0];
        const strength =
          body.status === "skipped" ? 0.25 : reading ? 0.55 : 0.4;
        this.edgeColors.set(
          [
            tint.r * strength,
            tint.g * strength,
            tint.b * strength,
            tint.r * strength * 1.4,
            tint.g * strength * 1.4,
            tint.b * strength * 1.4,
          ],
          edge * 6,
        );
        edge++;
      }

      for (const f of body.frontier) {
        if (star >= MAX_FRONTIER) break;
        const p = this.frontierWorld(body, f, now);
        const fade = this.reducedMotion
          ? 1
          : easeOutCubic(Math.min(1, (now - body.settledAt) / 1.2));
        p.lerpVectors(body.pos, p, fade);
        this.frontierPositions.set([p.x, p.y, p.z], star * 3);
        star++;
      }
    }
    const frontierGeometry = this.frontierPoints.geometry;
    frontierGeometry.setDrawRange(0, star);
    frontierGeometry.attributes.position.needsUpdate = true;
    const edgeGeometry = this.edgeLines.geometry;
    edgeGeometry.setDrawRange(0, edge * 2);
    edgeGeometry.attributes.position.needsUpdate = true;
    edgeGeometry.attributes.color.needsUpdate = true;
  }

  private frameCamera(dt: number) {
    const list = [...this.bodies.values()];
    const target = new THREE.Vector3();
    const chosen = this.lookup(this.selected);
    if (chosen) target.copy(chosen.pos);
    else if (list.length) {
      for (const body of list) target.add(body.pos);
      target.divideScalar(list.length);
    }
    this.center.lerp(target, 1 - Math.exp(-3 * dt));
    let radius = 1.5;
    for (const body of list)
      radius = Math.max(radius, body.pos.distanceTo(this.center) + 1.2);
    const aspect = this.camera.aspect;
    const fit =
      (radius / Math.tan((this.camera.fov * Math.PI) / 360)) *
      0.95 *
      (aspect < 1 ? 1.15 / aspect : 1);
    const desired = THREE.MathUtils.clamp(chosen ? fit * 0.7 : fit, 4.5, 24);
    const offset = new THREE.Vector3().subVectors(
      this.camera.position,
      this.controls.target,
    );
    const length = offset.length();
    offset.setLength(length + (desired - length) * (1 - Math.exp(-2 * dt)));
    this.controls.target.copy(this.center);
    this.camera.position.copy(this.center).add(offset);
  }

  private project(position: THREE.Vector3): {
    x: number;
    y: number;
    visible: boolean;
  } {
    const v = position.clone().project(this.camera);
    const { clientWidth: w, clientHeight: h } = this.host;
    return { x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h, visible: v.z < 1 };
  }

  private label(
    id: string,
    text: string,
    kind: "title" | "count",
  ): HTMLDivElement {
    let element = this.labels.get(id);
    if (!element) {
      element = document.createElement("div");
      this.overlay.appendChild(element);
      this.labels.set(id, element);
    }
    const className =
      kind === "count"
        ? "absolute left-0 top-0 whitespace-nowrap rounded-full bg-amber-400/90 px-1.5 py-px text-[10px] font-semibold text-amber-950 shadow"
        : "absolute left-0 top-0 max-w-[220px] truncate rounded-md bg-slate-950/80 px-2 py-0.5 text-[11px] font-medium text-slate-100 ring-1 ring-white/10 backdrop-blur";
    if (element.className !== className) element.className = className;
    if (element.textContent !== text) element.textContent = text;
    return element;
  }

  private placeLabels() {
    const shown = new Set<string>();
    for (const body of this.bodies.values()) {
      const cited = this.citations[body.finalUrl] ?? 0;
      const titled =
        body.id === this.hovered ||
        body.id === this.selected ||
        body.depth === 0;
      if (!titled && !cited) continue;
      const { x, y, visible } = this.project(body.pos);
      if (!visible) continue;
      const element = titled
        ? this.label(
            body.id,
            body.status === "skipped" ? `Skipped · ${body.title}` : body.title,
            "title",
          )
        : this.label(
            body.id,
            `${cited} ${cited === 1 ? "value" : "values"}`,
            "count",
          );
      const dy = titled ? -34 : 14;
      element.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y + dy)}px, 0) translateX(-50%)`;
      shown.add(body.id);
    }
    for (const [id, element] of this.labels) {
      if (!shown.has(id)) {
        element.remove();
        this.labels.delete(id);
      }
    }
  }

  private nearest(x: number, y: number): string | null {
    let best: string | null = null;
    let bestDistance = 26;
    for (const body of this.bodies.values()) {
      const p = this.project(body.pos);
      if (!p.visible) continue;
      const distance = Math.hypot(p.x - x, p.y - y);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = body.id;
      }
    }
    return best;
  }

  private local(event: PointerEvent) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  private handleMove = (event: PointerEvent) => {
    this.pointer = this.local(event);
    this.hovered = this.nearest(this.pointer.x, this.pointer.y);
    this.renderer.domElement.style.cursor = this.hovered ? "pointer" : "grab";
  };

  private handleLeave = () => {
    this.pointer = null;
    this.hovered = null;
  };

  private handleDown = (event: PointerEvent) => {
    this.down = this.local(event);
  };

  private handleUp = (event: PointerEvent) => {
    const up = this.local(event);
    if (this.down && Math.hypot(up.x - this.down.x, up.y - this.down.y) < 6) {
      this.onSelect(this.nearest(up.x, up.y));
    }
    this.down = null;
  };

  private handleDragStart = () => {
    // Taking hold of the scene stops the drift; the button starts it again.
    if (this.rotating) this.setRotating(false);
  };

  private resize() {
    const { clientWidth: w, clientHeight: h } = this.host;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    this.resizer.disconnect();
    const canvas = this.renderer.domElement;
    canvas.removeEventListener("pointermove", this.handleMove);
    canvas.removeEventListener("pointerleave", this.handleLeave);
    canvas.removeEventListener("pointerdown", this.handleDown);
    canvas.removeEventListener("pointerup", this.handleUp);
    this.controls.removeEventListener("start", this.handleDragStart);
    this.controls.dispose();
    for (const body of [...this.bodies.values()]) this.remove(body);
    for (const object of [this.frontierPoints, this.edgeLines]) {
      object.geometry.dispose();
      (object.material as THREE.Material).dispose();
    }
    this.sphere.dispose();
    this.glowMap.dispose();
    this.ringMap.dispose();
    this.renderer.dispose();
    canvas.remove();
    this.overlay.replaceChildren();
  }
}

export default function Constellation({
  nodes,
  phase,
  citations,
  selected,
  onSelect,
  className,
}: ConstellationProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<CrawlScene | null>(null);
  const [failed, setFailed] = useState(false);
  const [rotating, setRotating] = useState(true);

  useEffect(() => {
    if (!hostRef.current || !overlayRef.current) return;
    let scene: CrawlScene;
    try {
      scene = new CrawlScene(hostRef.current, overlayRef.current);
    } catch {
      // No WebGL: the page list below still shows every page.
      queueMicrotask(() => setFailed(true));
      return;
    }
    sceneRef.current = scene;
    scene.onRotatingChange = setRotating;
    queueMicrotask(() => setRotating(scene.rotating));
    return () => {
      scene.dispose();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (sceneRef.current) sceneRef.current.onSelect = onSelect;
  }, [onSelect]);

  useEffect(() => {
    sceneRef.current?.sync(nodes, phase, citations, selected);
  }, [nodes, phase, citations, selected]);

  const pages = nodes.filter((node) => node.status === "page").length;

  return (
    <div
      className={cn("relative overflow-hidden", className)}
      role="img"
      aria-label={
        pages
          ? `Site map of the crawl: ${pages} pages, each linked from the page it was found on`
          : "Site map of the crawl"
      }
    >
      <div ref={hostRef} className="absolute inset-0" />
      <div
        ref={overlayRef}
        className="pointer-events-none absolute inset-0"
        aria-hidden
      />
      {failed && (
        <p className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-slate-300">
          The 3D view needs WebGL. Every page is listed below.
        </p>
      )}
      {!failed && (
        <button
          type="button"
          onClick={() => sceneRef.current?.setRotating(!rotating)}
          className="absolute right-3 bottom-3 grid size-9 place-items-center rounded-full bg-white/10 text-slate-200 ring-1 ring-white/15 backdrop-blur transition hover:bg-white/20 focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:outline-none"
          aria-label={rotating ? "Pause rotation" : "Resume rotation"}
          title={rotating ? "Pause rotation" : "Resume rotation"}
        >
          {rotating ? (
            <Pause className="size-4" />
          ) : (
            <Play className="size-4" />
          )}
        </button>
      )}
    </div>
  );
}
