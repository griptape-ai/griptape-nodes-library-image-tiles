# Image Tiles

A [Griptape Nodes](https://www.griptapenodes.com/) library for splitting images into tiles for external editing, merging them back together, and working with equirectangular 360° panoramas.

---

## Why Image Tiles?

Large images are hard to edit all at once. Tiling lets you break them into manageable pieces, send each one through a pipeline (upscaler, inpainter, style transfer — whatever you need), and stitch everything cleanly back together.

The same library also handles the panorama side: convert any flat image into a 2:1 equirectangular canvas, smooth the seam where it wraps, and preview the result as an interactive 360° sphere — all inside the node graph.

Use it to:

- **Edit large images in sections** — split a high-res image into 512px tiles, process each one individually, merge back to the original size
- **Upscale beyond model limits** — tile a large image, upscale each tile separately, reassemble seamlessly
- **Create 360° environments** — convert AI-generated images into equirectangular panoramas ready for viewing or export
- **Fix panorama seams** — blend the left/right wrap point on equirectangular images so the seam disappears

---

## Nodes

### Image Tile Splitter

Cuts an image into a grid of square tiles and writes each one to disk. Outputs a **Manifest JSON** describing the grid layout and the location of every tile — connect this to an **Image Tile Merger** to reassemble.

**Inputs**

| Parameter | Description |
|---|---|
| Image | The source image to split |
| Tile Size | Square tile size in pixels (default: 512) |
| Pad to Fit | Pad the image to a full tile grid so edge tiles are always the same size |
| Tile File | Output filename for tiles — set a subdirectory here (e.g. `my_project/tile.png`) to keep tiles organized |

**Outputs**

| Parameter | Description |
|---|---|
| Tile Count | Total number of tiles produced |
| Rows | Number of tile rows |
| Columns | Number of tile columns |
| Manifest JSON | Grid metadata and tile URLs — wire this to an Image Tile Merger |

---

### Image Tile Merger

Reads a **Manifest JSON** from an **Image Tile Splitter**, loads all the tiles, and reassembles them into a single image cropped to the original dimensions. Optionally softens tile seams with a Gaussian blur.

**Inputs**

| Parameter | Description |
|---|---|
| Manifest JSON | Grid manifest from an Image Tile Splitter |
| Seam Blur (px) | Blur radius applied along internal tile boundaries (0 = disabled) |

**Outputs**

| Parameter | Description |
|---|---|
| Merged Image | The reassembled image |
| Width | Output width in pixels |
| Height | Output height in pixels |

---

### 360 Seam Blend

Blends the left and right edges of an equirectangular panoramic image. When a panorama is wrapped into a sphere the left and right edges meet — if they don't match, you see a hard seam. This node fades them together so the join is invisible.

**Inputs**

| Parameter | Description |
|---|---|
| Image | Equirectangular panoramic image |
| Blend Width (px) | Width of the blend zone at the seam |
| Blend Mode | Curve shape across the blend zone: `cosine`, `linear`, or `smooth` |
| Seam Blur Radius | Optional Gaussian blur near the seam (0 = disabled) |
| Seam Blur Mix | Strength of the blur mix (0–1) |

**Outputs**

| Parameter | Description |
|---|---|
| Output Image | Seam-blended panoramic image |
| Width / Height | Output dimensions in pixels |
| Aspect Ratio | Output width ÷ height |

---

### To LatLong 2:1

Converts any image into a 2:1 equirectangular canvas — the standard format for 360° panoramas. Use this when your source image isn't already 2:1 (most AI-generated images aren't).

**Inputs**

| Parameter | Description |
|---|---|
| Image | Any source image |
| Output Width | Canvas width in pixels; height is always width ÷ 2 |
| Fit Mode | How to fill the canvas (see below) |
| Background Blur | Blur radius for the background fill in `pad_blur` mode |

**Fit modes**

| Mode | Behaviour |
|---|---|
| `pad_blur` | Centers the image; fills empty space with a blurred version of itself |
| `pad_black` | Centers the image on a black canvas |
| `crop` | Scales to fill the canvas and center-crops any overflow |
| `stretch` | Stretches the image to fit exactly — ignores aspect ratio |

**Outputs**

| Parameter | Description |
|---|---|
| Output Image | 2:1 equirectangular image |
| Width / Height | Output dimensions in pixels |
| Aspect Ratio | Should always be 2.0 |

---

### 360 Image Viewer

Displays an equirectangular image in an interactive spherical 360° viewer directly on the canvas. Drag to look around; scroll to zoom. Expects a 2:1 equirectangular image — run your image through **To LatLong 2:1** first if needed.

**Inputs**

| Parameter | Description |
|---|---|
| Image | Equirectangular (2:1) image to preview |
| HFov | Horizontal field of view in degrees (40–140, default 95) |

The viewer updates automatically when the node runs and resizes with the node.

---

## Workflows

### Edit a large image in tiles

```
Image → Image Tile Splitter → [process tiles externally] → Image Tile Merger → result
```

Set a descriptive subdirectory on **Tile File** (e.g. `my_project/tile.png`) to keep tiles organized. After editing, wire the **Manifest JSON** straight into **Image Tile Merger** — it knows where all the tiles are and how to put them back.

### Preview a flat image as a 360° panorama

```
Image → To LatLong 2:1 → 360 Seam Blend → 360 Image Viewer
```

`pad_blur` fit mode works well for most images — it fills the empty canvas with a blurred background rather than black bars.

### Tile-edit a panorama, then view it

```
Image → To LatLong 2:1 → Image Tile Splitter → [edit tiles] → Image Tile Merger → 360 Seam Blend → 360 Image Viewer
```

Split the equirectangular image into tiles for detailed editing, merge back, blend the seam, and preview — all inside a single graph.

---

## Installation

1. In Griptape Nodes, open **Manage → Library Management**
2. Paste in the repository URL: `https://github.com/griptape-ai/griptape-nodes-library-image-tiles.git`
3. Click **Download**

Once installed, look for the **Image Tiles** category in the node picker.

---

## License

Apache License 2.0
