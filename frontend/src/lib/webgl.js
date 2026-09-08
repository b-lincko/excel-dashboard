export function prefersReducedMotion() {
  try {
    return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);
  } catch {
    return false;
  }
}

export function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function disposeObject3D(root) {
  if (!root) return;
  root.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose?.();
    const mat = obj.material;
    if (!mat) return;
    const list = Array.isArray(mat) ? mat : [mat];
    list.forEach((m) => {
      if (m.map) m.map.dispose?.();
      m.dispose?.();
    });
  });
}
