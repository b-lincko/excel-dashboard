import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { disposeObject3D, prefersReducedMotion, webglAvailable } from "../lib/webgl.js";

const BRANCH_COLOR = {
  sites: 0x0ea5e9,
  status: 0x6366f1,
  blockades: 0xf43f5e,
  people: 0x8b5cf6,
  delivery: 0x14b8a6,
  priority: 0xf59e0b,
};

function layoutGraph(root, branches) {
  const nodes = [];
  const links = [];
  if (!root) return { nodes, links };
  nodes.push({
    id: root.id,
    label: root.label,
    value: Number(root.value) || 0,
    kind: "root",
    color: 0x0d9f8a,
    node: root,
    x: 0,
    y: 0,
    z: 0,
  });
  const list = branches || [];
  const n = Math.max(list.length, 1);
  list.forEach((branch, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    const radius = 3.5;
    const bx = Math.cos(angle) * radius;
    const by = Math.sin(i * 1.7) * 0.25;
    const bz = Math.sin(angle) * radius;
    const color = BRANCH_COLOR[branch.id] || 0x64748b;
    nodes.push({
      id: branch.id,
      label: branch.label,
      value: Number(branch.value) || 0,
      kind: "branch",
      color,
      node: branch,
      x: bx,
      y: by,
      z: bz,
    });
    links.push({ from: root.id, to: branch.id });
    const kids = (branch.children || []).slice(0, 10);
    kids.forEach((child, j) => {
      const spread = (j - (kids.length - 1) / 2) * 0.2;
      const ka = angle + spread;
      const kr = 6.15;
      const ky = ((j % 3) - 1) * 0.5 + by;
      nodes.push({
        id: child.id,
        label: child.label,
        value: Number(child.value) || 0,
        kind: "leaf",
        color,
        node: child,
        x: Math.cos(ka) * kr,
        y: ky,
        z: Math.sin(ka) * kr,
      });
      links.push({ from: branch.id, to: child.id });
      const grands = (child.children || []).slice(0, 5);
      grands.forEach((g, gi) => {
        const ga = ka + (gi - (grands.length - 1) / 2) * 0.1;
        nodes.push({
          id: g.id,
          label: g.label,
          value: Number(g.value) || 0,
          kind: "leaf2",
          color,
          node: g,
          x: Math.cos(ga) * 7.7,
          y: ky + 0.2,
          z: Math.sin(ga) * 7.7,
        });
        links.push({ from: child.id, to: g.id });
      });
    });
  });
  return { nodes, links };
}

function nodeRadius(item) {
  const v = Math.max(0, Number(item.value) || 0);
  const base = item.kind === "root" ? 0.42 : item.kind === "branch" ? 0.26 : 0.14;
  return Math.min(0.72, base + Math.log1p(v) * 0.055);
}

function graphFingerprint(root, branches) {
  const parts = [];
  function walk(n) {
    if (!n) return;
    parts.push(`${n.id}:${n.value ?? 0}:${n.open ?? ""}:${n.label || ""}`);
    (n.children || []).forEach(walk);
  }
  walk(root);
  (branches || []).forEach(walk);
  return parts.join("|");
}

function makeLabelSprite(text, dark) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const dpr = 2;
  const fontSize = 13;
  ctx.font = `600 ${fontSize}px ui-sans-serif, system-ui, sans-serif`;
  const padX = 10;
  const padY = 5;
  const tw = Math.ceil(ctx.measureText(text).width);
  const rw = tw + padX * 2;
  const rh = fontSize + padY * 2;
  canvas.width = rw * dpr;
  canvas.height = rh * dpr;
  const c = canvas.getContext("2d");
  c.scale(dpr, dpr);
  c.font = `600 ${fontSize}px ui-sans-serif, system-ui, sans-serif`;
  c.fillStyle = dark ? "rgba(15, 23, 42, 0.88)" : "rgba(255, 255, 255, 0.94)";
  c.strokeStyle = dark ? "rgba(148, 163, 184, 0.35)" : "rgba(15, 23, 42, 0.1)";
  c.lineWidth = 1;
  c.beginPath();
  if (c.roundRect) c.roundRect(0.5, 0.5, rw - 1, rh - 1, 8);
  else c.rect(0.5, 0.5, rw - 1, rh - 1);
  c.fill();
  c.stroke();
  c.fillStyle = dark ? "#f8fafc" : "#0f172a";
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillText(text, rw / 2, rh / 2 + 0.5);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false });
  const sprite = new THREE.Sprite(mat);
  const worldW = Math.min(2.6, Math.max(0.85, rw / 108));
  sprite.scale.set(worldW, worldW * (rh / rw), 1);
  sprite.center.set(0.5, 0);
  sprite.userData.texture = tex;
  return sprite;
}

export default function MindMap3D({ root, branches, selectedId, onSelect }) {
  const hostRef = useRef(null);
  const onSelectRef = useRef(onSelect);
  const selectedRef = useRef(selectedId);
  const graphRef = useRef({ root, branches });
  const [hover, setHover] = useState("");
  const [ready, setReady] = useState(false);

  onSelectRef.current = onSelect;
  selectedRef.current = selectedId;
  graphRef.current = { root, branches };

  const fingerprint = useMemo(() => graphFingerprint(root, branches), [root, branches]);

  useEffect(() => {
    const host = hostRef.current;
    const { root: graphRoot, branches: graphBranches } = graphRef.current;
    if (!host || !graphRoot || !webglAvailable()) return undefined;

    const reduced = prefersReducedMotion();
    const dark = document.documentElement.classList.contains("dark");
    const { nodes, links } = layoutGraph(graphRoot, graphBranches);
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const rootId = graphRoot.id;

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(dark ? 0x0b1220 : 0xf8fafc, 12, 22);

    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 80);
    camera.position.set(0, 4.2, 11.5);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.setAttribute("aria-label", "3D mind map of live material-request counts");

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 6;
    controls.maxDistance = 18;
    controls.autoRotate = !reduced;
    controls.autoRotateSpeed = 0.55;
    controls.target.set(0, 0, 0);

    scene.add(new THREE.AmbientLight(0xffffff, dark ? 0.55 : 0.8));
    const key = new THREE.DirectionalLight(0xffffff, dark ? 0.85 : 0.65);
    key.position.set(4, 8, 6);
    scene.add(key);
    const fill = new THREE.PointLight(0x12a38c, 1.1, 18);
    fill.position.set(-3, 2, 4);
    scene.add(fill);

    const group = new THREE.Group();
    scene.add(group);

    const sphere = new THREE.SphereGeometry(1, 28, 20);
    const meshes = [];
    const sprites = [];
    nodes.forEach((item) => {
      const mat = new THREE.MeshStandardMaterial({
        color: item.color,
        roughness: 0.35,
        metalness: 0.18,
        emissive: item.color,
        emissiveIntensity: item.kind === "root" ? 0.35 : 0.12,
      });
      const mesh = new THREE.Mesh(sphere, mat);
      const r = nodeRadius(item);
      mesh.scale.setScalar(r);
      mesh.position.set(item.x, item.y, item.z);
      mesh.userData = {
        id: item.id,
        node: item.node,
        baseY: item.y,
        radius: r,
        label: item.label,
        value: item.value,
        kind: item.kind,
      };
      const caption = `${item.label} · ${item.value}`;
      const sprite = makeLabelSprite(caption.length > 28 ? `${item.label.slice(0, 18)}… · ${item.value}` : caption, dark);
      sprite.position.set(0, 1.15, 0);
      mesh.add(sprite);
      sprites.push(sprite);
      group.add(mesh);
      meshes.push(mesh);
    });

    const linePos = [];
    links.forEach((link) => {
      const a = byId[link.from];
      const b = byId[link.to];
      if (!a || !b) return;
      linePos.push(a.x, a.y, a.z, b.x, b.y, b.z);
    });
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePos, 3));
    const lineMesh = new THREE.LineSegments(
      lineGeo,
      new THREE.LineBasicMaterial({
        color: dark ? 0x94a3b8 : 0x64748b,
        transparent: true,
        opacity: 0.35,
      })
    );
    group.add(lineMesh);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let frame = 0;
    let running = true;
    let visible = true;

    function size() {
      const w = host.clientWidth || 1;
      const h = Math.max(host.clientHeight || 1, 320);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }
    size();
    const ro = new ResizeObserver(size);
    ro.observe(host);

    const io = new IntersectionObserver(
      (entries) => {
        visible = entries.some((e) => e.isIntersecting);
      },
      { threshold: 0.05 }
    );
    io.observe(host);

    function applySelection() {
      const sid = selectedRef.current;
      meshes.forEach((mesh) => {
        const on = mesh.userData.id === sid;
        mesh.material.emissiveIntensity = on ? 0.72 : mesh.userData.id === rootId ? 0.35 : 0.12;
        mesh.scale.setScalar(mesh.userData.radius * (on ? 1.28 : 1));
      });
    }

    function pickFromEvent(event) {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(meshes, false);
      return hits[0]?.object || null;
    }

    function onMove(event) {
      const hit = pickFromEvent(event);
      renderer.domElement.style.cursor = hit ? "pointer" : "grab";
      controls.autoRotate = !reduced && !hit;
      if (!hit) {
        setHover("");
        return;
      }
      setHover(`${hit.userData.label} · ${hit.userData.value}`);
    }

    function onLeave() {
      controls.autoRotate = !reduced;
      setHover("");
      renderer.domElement.style.cursor = "grab";
    }

    function onClick(event) {
      const hit = pickFromEvent(event);
      if (hit?.userData.node) onSelectRef.current?.(hit.userData.node);
    }

    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);
    renderer.domElement.addEventListener("click", onClick);

    const clock = new THREE.Clock();
    function tick() {
      if (!running) return;
      requestAnimationFrame(tick);
      if (!visible) return;
      const t = clock.getElapsedTime();
      meshes.forEach((mesh, i) => {
        mesh.position.y = mesh.userData.baseY + Math.sin(t * 1.1 + i * 0.45) * 0.07;
      });
      applySelection();
      controls.update();
      renderer.render(scene, camera);
      frame += 1;
      if (frame === 1) setReady(true);
    }
    tick();

    return () => {
      running = false;
      io.disconnect();
      ro.disconnect();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      renderer.domElement.removeEventListener("click", onClick);
      controls.dispose();
      sprites.forEach((sprite) => {
        sprite.userData.texture?.dispose();
        sprite.material?.dispose();
      });
      disposeObject3D(scene);
      sphere.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
    };
  }, [fingerprint]);

  if (!root) return null;

  return (
    <div className="relative min-h-[380px] h-[min(52vh,520px)] bg-gradient-to-b from-slate-50 to-white dark:from-ink-900 dark:to-ink-800">
      <div ref={hostRef} className="absolute inset-0 min-h-[380px]" />
      {!ready && (
        <div className="absolute inset-0 grid place-items-center text-xs text-slate-400">Preparing 3D map…</div>
      )}
      <div className="absolute left-3 bottom-3 right-3 flex items-end justify-between gap-3 pointer-events-none">
        <div className="rounded-full bg-white/85 dark:bg-ink-900/80 px-2.5 py-1 text-[11px] text-slate-500 shadow-sm">
          Drag to orbit · click a node · counts are live
        </div>
        {hover ? (
          <div className="rounded-full bg-brand-700 text-white px-2.5 py-1 text-[11px] font-semibold shadow-sm">{hover}</div>
        ) : null}
      </div>
    </div>
  );
}
