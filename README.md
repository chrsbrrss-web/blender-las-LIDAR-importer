# Blender LAS Point Cloud Importer

A Blender addon for importing LAS and LAZ point cloud files as mesh vertices or native point cloud objects. Works out of the box with no dependencies for standard `.las` files — LAZ support available via a one-click install.

Tested on Blender 5.x.


---

## Features

- **Zero-dependency LAS import** — built-in pure-Python reader works immediately with no setup
- **LAZ support** — one-click laspy install directly from the import dialog or Preferences
- **Point decimation** — limit import to any point count via uniform stride or random sampling; essential for large survey files
- **Color sources** — RGB, intensity (greyscale), or classification (rainbow hue mapping)
- **Center at origin** — automatically subtracts centroid so georeferenced data (coordinates like 400000, 4500000) lands at world origin
- **Import modes** — mesh vertices (all Blender versions) or native Point Cloud object (Blender 3.3+)
- **Multi-file import** — select multiple files at once, each becomes its own object
- **LiDAR Info panel** — N-panel sidebar shows LAS version, point format, point count, scale, offset, min/max bounds, creation date, GPS time type, and return counts for any imported object
- **LAS 1.0–1.4** support, point record formats 0–10

---

## Installation

1. Download `io_import_las.py`
2. In Blender: **Edit > Preferences > Add-ons > Install…** and select the file
3. Enable **"Import-Export: LAS Point Cloud Importer"**
4. Access via **File > Import > LAS Point Cloud (.las/.laz)**

### LAZ support (optional)

LAZ files require the `laspy` library. Install it without leaving Blender:

- Open the import dialog (**File > Import > LAS Point Cloud**)
- If laspy is missing, an **Install laspy** button appears at the top of the options panel
- Click it and wait ~30 seconds

Alternatively, from **Edit > Preferences > Add-ons**, find the addon and click **Install laspy** in the preferences panel.

Or manually via terminal:
```
"<blender_python_path>" -m pip install laspy[lazrs]
```
Then restart Blender.

---

## Usage

### Import options

| Option | Description |
|---|---|
| **Import As** | Mesh (vertices) or Point Cloud object (Blender 3.3+) |
| **Max Points** | Cap the number of imported points. 0 = import all. Default 500,000 |
| **Decimate Method** | Uniform stride (evenly spaced) or Random sample |
| **Center at Origin** | Subtract centroid — use this for any georeferenced/survey data |
| **Color Source** | RGB, Intensity (greyscale), Classification (hue), or None |
| **Intensity → Vertex Weight** | Also stores intensity as a vertex group weight (mesh mode) |

### Viewing colors in the viewport

After import, add a material to the object:
1. **Material Properties > New**
2. In the Shader Editor, add an **Attribute** node, set Name to `LAS_Color`
3. Connect **Color** output to **Base Color** on the Principled BSDF

### LiDAR Info panel

Select any imported LAS object and open the **N-panel** (press N in the viewport) > **LiDAR** tab to see the full header metadata.

### Working with the point cloud

A few useful next steps after import:

**Generate terrain mesh from ground points:**
1. Separate ground points (usually classification 2) into their own object
2. Create a Plane scaled to cover the area, subdivide heavily (100+ cuts)
3. Add a **Shrinkwrap** modifier: Target = point cloud, Mode = Project, Negative Z

**Generate building mesh:**
1. Add a **Geometry Nodes** modifier
2. Build: Points to Volume (Radius 0.1–0.3m) → Volume to Mesh
3. Follow with a **Remesh** modifier in Voxel mode for clean topology

**Select points and create a face:**
In Edit Mode, select any 4 coplanar vertices and press **F**

---

## Compatibility

| Blender | Status |
|---|---|
| 5.x | ✅ Tested |

---

## Known limitations

- The built-in reader loads the entire file into memory before processing — for very large files (1GB+) use laspy which handles chunked reading
- The pure-Python reader covers standard LAS 1.0–1.4. Some LAS 1.4 files with extra byte records or exotic VLRs may need laspy to parse correctly
- LAZ files always require laspy — there is no fallback

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.
