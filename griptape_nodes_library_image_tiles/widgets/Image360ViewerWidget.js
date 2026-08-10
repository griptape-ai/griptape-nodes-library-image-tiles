/**
 * Image360ViewerWidget
 * Equirectangular 360 viewer using Pannellum (loaded from CDN on first use).
 * Follows the Griptape Nodes widget contract: returns { cleanup, update }.
 */

let pannellumLoadPromise = null;

function loadPannellum() {
  if (window.pannellum) return Promise.resolve(window.pannellum);
  if (pannellumLoadPromise) return pannellumLoadPromise;

  pannellumLoadPromise = new Promise((resolve, reject) => {
    const cssId = "gtn-pannellum-css";
    if (!document.getElementById(cssId)) {
      const link = document.createElement("link");
      link.id = cssId;
      link.rel = "stylesheet";
      link.href = "https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css";
      document.head.appendChild(link);
    }
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js";
    script.async = true;
    script.onload = () => resolve(window.pannellum);
    script.onerror = () => reject(new Error("Failed to load Pannellum assets."));
    document.body.appendChild(script);
  });

  return pannellumLoadPromise;
}

function normalizeValue(raw) {
  if (!raw) return { image_url: "", hfov: 95 };
  if (typeof raw === "string") return { image_url: raw, hfov: 95 };
  return {
    image_url: String(raw.image_url || "").trim(),
    hfov: Number.isFinite(Number(raw.hfov)) ? Number(raw.hfov) : 95,
  };
}

function clampHfov(hfov) {
  return Math.max(40, Math.min(140, Number(hfov) || 95));
}

export default function Image360ViewerWidget(container, props) {
  if (container._image360Instance?.wrapper?.isConnected) {
    container._image360Instance.handleUpdate(props);
    return {
      cleanup: container._image360Instance.cleanup,
      update: container._image360Instance.handleUpdate,
    };
  }

  const { value } = props;
  const state = normalizeValue(value);

  // Wrapper fills the full node width/height allocated by the framework.
  const wrapper = document.createElement("div");
  wrapper.className = "nodrag nowheel";
  wrapper.style.cssText = "display:flex;flex-direction:column;gap:8px;padding:6px;background:#101010;border-radius:6px;width:100%;height:100%;box-sizing:border-box;";

  // Host fills the remaining flex space; Pannellum sizes itself to this element.
  const host = document.createElement("div");
  host.style.cssText = "width:100%;flex:1 1 0;min-height:200px;background:#000;border-radius:6px;overflow:hidden;";
  host.className = "nodrag nowheel";

  const note = document.createElement("div");
  note.style.cssText = "font-size:11px;color:#8a8a8a;flex-shrink:0;";
  note.textContent = "Drag: rotate | Wheel: zoom";

  wrapper.appendChild(host);
  wrapper.appendChild(note);
  container.appendChild(wrapper);

  wrapper.addEventListener("pointerdown", (e) => e.stopPropagation());
  wrapper.addEventListener("mousedown", (e) => e.stopPropagation());
  wrapper.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });

  let viewer = null;
  let currentUrl = "";

  function renderMessage(text) {
    host.innerHTML =
      `<div style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#777;font-size:12px;text-align:center;padding:12px;">${text}</div>`;
  }

  function renderViewer(imageUrl, hfov) {
    if (!imageUrl) {
      if (viewer) {
        try { viewer.destroy(); } catch (_) {}
        viewer = null;
        currentUrl = "";
      }
      renderMessage("Connect an image and run the node.");
      return;
    }

    if (viewer && currentUrl === imageUrl) {
      try { viewer.setHfov(clampHfov(hfov)); } catch (_) {}
      return;
    }

    if (viewer) {
      try { viewer.destroy(); } catch (_) {}
      viewer = null;
    }

    host.innerHTML = "";
    currentUrl = imageUrl;

    viewer = window.pannellum.viewer(host, {
      type: "equirectangular",
      panorama: imageUrl,
      autoLoad: true,
      showControls: true,
      mouseZoom: true,
      draggable: true,
      compass: false,
      hfov: clampHfov(hfov),
      minHfov: 35,
      maxHfov: 140,
    });
  }

  // Notify Pannellum when the host element is resized so it redraws correctly.
  const resizeObserver = new ResizeObserver(() => {
    if (viewer) {
      try { viewer.resize(); } catch (_) {}
    }
  });
  resizeObserver.observe(host);

  function handleUpdate(newProps) {
    const s = normalizeValue(newProps.value);
    loadPannellum()
      .then(() => renderViewer(s.image_url, s.hfov))
      .catch(() => renderMessage("Could not load 360 viewer assets."));
  }

  function cleanup() {
    resizeObserver.disconnect();
    if (viewer) {
      try { viewer.destroy(); } catch (_) {}
      viewer = null;
    }
    wrapper.remove();
    delete container._image360Instance;
  }

  container._image360Instance = { wrapper, handleUpdate, cleanup };

  loadPannellum()
    .then(() => renderViewer(state.image_url, state.hfov))
    .catch(() => renderMessage("Could not load 360 viewer assets."));

  return { cleanup, update: handleUpdate };
}
