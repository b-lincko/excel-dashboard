import { useEffect, useRef } from "react";
import * as THREE from "three";
import { disposeObject3D, prefersReducedMotion, webglAvailable } from "../lib/webgl.js";

const COUNT = 72;

function seeded(i) {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

export default function LoginScene() {
  const hostRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !webglAvailable() || prefersReducedMotion()) return undefined;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 40);
    camera.position.set(0, 0.4, 9.5);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.setAttribute("aria-hidden", "true");

    const positions = new Float32Array(COUNT * 3);
    const pts = [];
    for (let i = 0; i < COUNT; i += 1) {
      const x = (seeded(i) - 0.5) * 10;
      const y = (seeded(i + 3) - 0.5) * 8;
      const z = (seeded(i + 9) - 0.5) * 8;
      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;
      pts.push(new THREE.Vector3(x, y, z));
    }

    const pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const points = new THREE.Points(
      pGeo,
      new THREE.PointsMaterial({
        color: 0xffffff,
        size: 0.085,
        transparent: true,
        opacity: 0.85,
        sizeAttenuation: true,
      })
    );
    scene.add(points);

    const lineVerts = [];
    for (let i = 0; i < COUNT; i += 1) {
      let best = -1;
      let bestD = 2.35;
      for (let j = i + 1; j < COUNT; j += 1) {
        const d = pts[i].distanceTo(pts[j]);
        if (d < bestD) {
          bestD = d;
          best = j;
        }
      }
      if (best >= 0) {
        lineVerts.push(pts[i].x, pts[i].y, pts[i].z, pts[best].x, pts[best].y, pts[best].z);
      }
    }
    const lGeo = new THREE.BufferGeometry();
    lGeo.setAttribute("position", new THREE.Float32BufferAttribute(lineVerts, 3));
    const lines = new THREE.LineSegments(
      lGeo,
      new THREE.LineBasicMaterial({ color: 0xc5eee6, transparent: true, opacity: 0.28 })
    );
    scene.add(lines);

    const glow = new THREE.PointLight(0x9ef0df, 2.2, 16);
    glow.position.set(1.5, 1.2, 3);
    scene.add(glow);
    scene.add(new THREE.AmbientLight(0xffffff, 0.35));

    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.55, 1),
      new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: 0x12a38c,
        emissiveIntensity: 0.7,
        roughness: 0.25,
        metalness: 0.35,
        wireframe: true,
      })
    );
    scene.add(core);

    function size() {
      const w = host.clientWidth || 1;
      const h = host.clientHeight || 1;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }
    size();
    const ro = new ResizeObserver(size);
    ro.observe(host);

    let running = true;
    let visible = true;
    const io = new IntersectionObserver(
      (entries) => {
        visible = entries.some((e) => e.isIntersecting);
      },
      { threshold: 0.05 }
    );
    io.observe(host);

    const clock = new THREE.Clock();
    function tick() {
      if (!running) return;
      requestAnimationFrame(tick);
      if (!visible) return;
      const t = clock.getElapsedTime();
      points.rotation.y = t * 0.05;
      lines.rotation.y = t * 0.05;
      core.rotation.y = t * 0.35;
      core.rotation.x = t * 0.18;
      glow.intensity = 1.8 + Math.sin(t * 1.4) * 0.4;
      renderer.render(scene, camera);
    }
    tick();

    return () => {
      running = false;
      io.disconnect();
      ro.disconnect();
      disposeObject3D(scene);
      renderer.dispose();
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={hostRef} className="absolute inset-0 pointer-events-none" aria-hidden="true" />;
}
