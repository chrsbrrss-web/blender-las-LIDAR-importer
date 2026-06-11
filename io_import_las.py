"""
Blender LAS Point Cloud Importer  v1.4
=======================================
Imports .las / .laz point cloud files into Blender as a mesh object
(vertices only) or as a native Point Cloud object (Blender 3.3+).

Supports LAS versions 1.0-1.4, point record formats 0-10.
LAZ (compressed) files require laspy[lazrs] — install via the button in
Edit > Preferences > Add-ons > LAS Point Cloud Importer.

Installation
------------
1. Save this file as  io_import_las.py
2. Blender > Edit > Preferences > Add-ons > Install… > pick the file
3. Enable  "Import-Export: LAS Point Cloud Importer"
4. File > Import > LAS Point Cloud (.las/.laz)

Blender compatibility: 3.x, 4.x, 5.x
"""

bl_info = {
    "name": "LAS Point Cloud Importer",
    "author": "Your Name",
    "version": (1, 4, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > LAS Point Cloud (.las/.laz)",
    "description": "Import LAS/LAZ point cloud files as mesh vertices or point clouds",
    "doc_url": "https://github.com/yourusername/blender-las-importer",
    "category": "Import-Export",
}

import os
import sys
import struct
import traceback

import bpy
import bmesh
from bpy.props import (
    StringProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
)
from bpy_extras.io_utils import ImportHelper


# ---------------------------------------------------------------------------
# Dependency management
# ---------------------------------------------------------------------------

def _site_packages_dir():
    """Return (and create if needed) a writable site-packages next to the addon."""
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    sp = os.path.join(addon_dir, "site-packages")
    os.makedirs(sp, exist_ok=True)
    return sp


def _ensure_on_path(sp):
    if sp not in sys.path:
        sys.path.insert(0, sp)


def _try_import_laspy():
    try:
        import laspy
        return laspy
    except ImportError:
        return None


def install_laspy(op=None):
    """
    Install laspy into a site-packages folder beside this addon.
    Returns (success: bool, message: str).
    """
    import subprocess

    sp = _site_packages_dir()
    _ensure_on_path(sp)
    python_exe = sys.executable

    try:
        import ensurepip
        ensurepip.bootstrap(user=False)
    except Exception:
        pass

    for pkg in ("laspy[lazrs]", "laspy"):
        try:
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "--quiet", "--target", sp, pkg],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode == 0:
                for mod in list(sys.modules.keys()):
                    if "laspy" in mod or "lazrs" in mod:
                        del sys.modules[mod]
                laspy = _try_import_laspy()
                if laspy is not None:
                    return True, f"laspy installed successfully ({pkg})."
        except Exception:
            continue

    return False, (
        "Auto-install failed. Open a terminal and run:\n"
        f"  \"{python_exe}\" -m pip install laspy[lazrs]\n"
        "then restart Blender."
    )


def get_laspy():
    """Return laspy module or None. Ensures addon site-packages is on sys.path."""
    sp = _site_packages_dir()
    _ensure_on_path(sp)
    return _try_import_laspy()


# ---------------------------------------------------------------------------
# Pure-Python fallback LAS reader (no dependencies, LAS only — not LAZ)
# ---------------------------------------------------------------------------

_POINT_SIZES = {0: 20, 1: 28, 2: 26, 3: 34, 4: 57, 5: 63,
                6: 30, 7: 36, 8: 38, 9: 59, 10: 67}

def _read_las_pure(filepath):
    """
    Minimal pure-Python LAS reader using only struct.
    Returns (xs, ys, zs, intensities, rgb_tuple, classifications, header_meta).
    RGB/intensity/classification may be None. Only handles uncompressed LAS.
    header_meta is a dict of raw header values for the info panel.
    """
    with open(filepath, "rb") as f:
        raw = f.read()

    sig = raw[:4]
    if sig != b"LASF":
        raise RuntimeError("Not a valid LAS file (bad signature).")

    ver_major   = raw[24]
    ver_minor   = raw[25]
    header_size = struct.unpack_from("<H", raw, 94)[0]
    offset_data = struct.unpack_from("<I", raw, 96)[0]
    pt_format   = raw[104] & 0x7F
    pt_length   = struct.unpack_from("<H", raw, 105)[0]

    if ver_major == 1 and ver_minor >= 4:
        num_points = struct.unpack_from("<Q", raw, 247)[0]
    else:
        num_points = struct.unpack_from("<I", raw, 107)[0]

    scale_x, scale_y, scale_z = struct.unpack_from("<ddd", raw, 131)
    off_x,   off_y,   off_z   = struct.unpack_from("<ddd", raw, 155)
    min_x,   min_y,   min_z   = struct.unpack_from("<ddd", raw, 187)
    max_x,   max_y,   max_z   = struct.unpack_from("<ddd", raw, 179)

    header_meta = {
        'version':      f"{ver_major}.{ver_minor}",
        'point_format': pt_format,
        'point_count':  num_points,
        'scale':        f"{scale_x:.6g}, {scale_y:.6g}, {scale_z:.6g}",
        'offset':       f"{off_x:.3f}, {off_y:.3f}, {off_z:.3f}",
        'min':          f"{min_x:.3f}, {min_y:.3f}, {min_z:.3f}",
        'max':          f"{max_x:.3f}, {max_y:.3f}, {max_z:.3f}",
    }

    has_rgb  = pt_format in (2, 3, 5, 7, 8, 10)
    cls_byte = 15 if pt_format <= 5 else 16
    rgb_offsets = {2: 20, 3: 28, 5: 28, 7: 30, 8: 30, 10: 30}
    rgb_off = rgb_offsets.get(pt_format, None)

    xs, ys, zs, intensities, reds, greens, blues, classifications = [], [], [], [], [], [], [], []
    data_block = raw[offset_data:]

    for i in range(num_points):
        base  = i * pt_length
        chunk = data_block[base: base + pt_length]
        if len(chunk) < 12:
            break

        raw_x, raw_y, raw_z = struct.unpack_from("<iii", chunk, 0)
        xs.append(raw_x * scale_x + off_x)
        ys.append(raw_y * scale_y + off_y)
        zs.append(raw_z * scale_z + off_z)

        if len(chunk) > 14:
            intensities.append(struct.unpack_from("<H", chunk, 12)[0])
        if len(chunk) > cls_byte:
            classifications.append(chunk[cls_byte])
        if has_rgb and rgb_off and len(chunk) >= rgb_off + 6:
            r, g, b = struct.unpack_from("<HHH", chunk, rgb_off)
            reds.append(r); greens.append(g); blues.append(b)

    return (
        xs, ys, zs,
        intensities if intensities else None,
        (reds, greens, blues) if reds else None,
        classifications if classifications else None,
        header_meta,
    )


# ---------------------------------------------------------------------------
# Core import logic
# ---------------------------------------------------------------------------

def read_las_file(filepath, max_points, decimate_method,
                  apply_offset, color_source, intensity_as_weight):
    """
    Read a LAS/LAZ file. Tries laspy first; falls back to pure-Python for .las.
    Returns a dict with coords, colors, weights, point_count, offset, scale,
    used_laspy, and header_meta.
    """
    import numpy as np

    laspy    = get_laspy()
    use_laspy = laspy is not None

    if not use_laspy and filepath.lower().endswith(".laz"):
        raise RuntimeError(
            "LAZ files require laspy. Use the 'Install laspy' button in "
            "Edit > Preferences > Add-ons, or install it manually and restart Blender."
        )

    # ---- read ----------------------------------------------------------------
    if use_laspy:
        try:
            las = laspy.read(filepath)
        except Exception as e:
            raise RuntimeError(f"laspy failed to read file: {e}")

        header      = las.header
        scale       = tuple(header.scales)
        total       = len(las.x)
        xs = np.asarray(las.x, dtype=np.float64)
        ys = np.asarray(las.y, dtype=np.float64)
        zs = np.asarray(las.z, dtype=np.float64)

        def _arr(attr):
            return np.asarray(getattr(las, attr)) if hasattr(las, attr) else None

        raw_r   = _arr('red');   raw_g = _arr('green'); raw_b = _arr('blue')
        raw_int = _arr('intensity')
        raw_cls = _arr('classification')

        # Build header metadata dict for info panel
        def _hv(attr, default="N/A"):
            v = getattr(header, attr, None)
            return str(v) if v is not None else default

        offsets = getattr(header, 'offsets', (0, 0, 0))
        scales  = getattr(header, 'scales',  (1, 1, 1))
        mins    = getattr(header, 'mins',    None)
        maxs    = getattr(header, 'maxs',    None)

        header_meta = {
            'version':      f"{getattr(header, 'version', 'N/A')}",
            'point_format': str(getattr(las.point_format, 'id', 'N/A')),
            'point_count':  total,
            'scale':        f"{scales[0]:.6g}, {scales[1]:.6g}, {scales[2]:.6g}",
            'offset':       f"{offsets[0]:.3f}, {offsets[1]:.3f}, {offsets[2]:.3f}",
            'min':          str(mins) if mins is not None else "N/A",
            'max':          str(maxs) if maxs is not None else "N/A",
            'creation_date':    _hv('creation_date'),
            'gps_time_type':    _hv('gps_time_type'),
            'point_count_by_return': _hv('point_count_by_return'),
        }

    else:
        px, py, pz, p_int, p_rgb, p_cls, header_meta = _read_las_pure(filepath)
        scale = (1.0, 1.0, 1.0)
        total = len(px)
        xs = np.array(px, dtype=np.float64)
        ys = np.array(py, dtype=np.float64)
        zs = np.array(pz, dtype=np.float64)
        raw_r  = np.array(p_rgb[0], dtype=np.float32) if p_rgb else None
        raw_g  = np.array(p_rgb[1], dtype=np.float32) if p_rgb else None
        raw_b  = np.array(p_rgb[2], dtype=np.float32) if p_rgb else None
        raw_int = np.array(p_int, dtype=np.float32) if p_int else None
        raw_cls = np.array(p_cls, dtype=np.uint8)  if p_cls else None
        header_meta['creation_date']         = "N/A"
        header_meta['gps_time_type']         = "N/A"
        header_meta['point_count_by_return'] = "N/A"

    if total == 0:
        raise RuntimeError("LAS file contains no points.")

    # ---- decimation ----------------------------------------------------------
    if max_points > 0 and total > max_points:
        if decimate_method == 'RANDOM':
            rng = np.random.default_rng(0)
            idx = rng.choice(total, size=max_points, replace=False)
            idx.sort()
        else:
            step = total / max_points
            idx  = np.clip(
                np.round(np.arange(max_points) * step).astype(int), 0, total - 1
            )
        xs, ys, zs = xs[idx], ys[idx], zs[idx]
        def _sub(a): return a[idx] if a is not None else None
        raw_r, raw_g, raw_b = _sub(raw_r), _sub(raw_g), _sub(raw_b)
        raw_int = _sub(raw_int)
        raw_cls = _sub(raw_cls)

    # ---- center --------------------------------------------------------------
    if apply_offset:
        cx, cy, cz = float(xs.mean()), float(ys.mean()), float(zs.mean())
        xs, ys, zs = xs - cx, ys - cy, zs - cz
    else:
        cx = cy = cz = 0.0

    coords = list(zip(xs.tolist(), ys.tolist(), zs.tolist()))

    # ---- colors --------------------------------------------------------------
    colors = weights = None

    if color_source == 'RGB' and raw_r is not None:
        r = raw_r.astype(np.float32)
        g = raw_g.astype(np.float32)
        b = raw_b.astype(np.float32)
        mv = 65535.0 if float(r.max()) > 255.0 else 255.0
        r /= mv; g /= mv; b /= mv
        colors = list(zip(r.tolist(), g.tolist(), b.tolist(), [1.0]*len(r)))

    elif color_source == 'INTENSITY' and raw_int is not None:
        v  = raw_int.astype(np.float32)
        mx = float(v.max())
        if mx > 0: v /= mx
        colors = list(zip(v.tolist(), v.tolist(), v.tolist(), [1.0]*len(v)))
        if intensity_as_weight:
            weights = v.tolist()

    elif color_source == 'CLASSIFICATION' and raw_cls is not None:
        import colorsys
        hues    = (raw_cls.astype(np.float32) / 31.0) % 1.0
        rgb_list = [colorsys.hsv_to_rgb(float(h), 0.85, 0.9) for h in hues]
        colors  = [(r, g, b, 1.0) for r, g, b in rgb_list]

    return {
        'coords':      coords,
        'colors':      colors,
        'weights':     weights,
        'point_count': len(coords),
        'offset':      (cx, cy, cz),
        'scale':       scale,
        'used_laspy':  use_laspy,
        'header_meta': header_meta,
    }


# ---------------------------------------------------------------------------
# Blender object creation
# ---------------------------------------------------------------------------

def create_blender_object(context, data, obj_name, import_mode):
    coords = data['coords']
    colors = data['colors']
    meta   = data['header_meta']

    if import_mode == 'POINTCLOUD' and bpy.app.version >= (3, 3, 0):
        obj = _create_pointcloud_object(context, obj_name, coords, colors)
    else:
        obj = _create_mesh_object(context, obj_name, coords, colors)

    # Store LAS header metadata as custom properties (drives the info panel)
    obj['las_version']              = meta.get('version', 'N/A')
    obj['las_point_format']         = str(meta.get('point_format', 'N/A'))
    obj['las_point_count']          = meta.get('point_count', 0)
    obj['las_scale']                = meta.get('scale', 'N/A')
    obj['las_offset']               = meta.get('offset', 'N/A')
    obj['las_min']                  = meta.get('min', 'N/A')
    obj['las_max']                  = meta.get('max', 'N/A')
    obj['las_creation_date']        = meta.get('creation_date', 'N/A')
    obj['las_gps_time_type']        = meta.get('gps_time_type', 'N/A')
    obj['las_point_count_by_return']= meta.get('point_count_by_return', 'N/A')

    return obj


def _create_mesh_object(context, name, coords, colors):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(coords, [], [])
    mesh.update()
    if colors:
        vcol = mesh.vertex_colors.new(name="LAS_Color")
        for loop in mesh.loops:
            vcol.data[loop.index].color = colors[loop.vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    return obj


def _create_pointcloud_object(context, name, coords, colors):
    import numpy as np
    pc = bpy.data.pointclouds.new(name)
    n  = len(coords)
    pc.points.add(n)
    pc.points.foreach_set("position",
                          np.array(coords, dtype=np.float32).flatten())
    if colors:
        attr = pc.attributes.new("color", 'FLOAT_COLOR', 'POINT')
        attr.data.foreach_set("color",
                              [ch for rgba in colors for ch in rgba])
    obj = bpy.data.objects.new(name, pc)
    context.collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# Install operator
# ---------------------------------------------------------------------------

class LAS_OT_install_laspy(bpy.types.Operator):
    """Install the laspy library into the addon's site-packages folder"""
    bl_idname  = "las.install_laspy"
    bl_label   = "Install laspy"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        self.report({'INFO'}, "Installing laspy, please wait…")
        ok, msg = install_laspy(self)
        self.report({'INFO'} if ok else {'ERROR'}, msg)
        return {'FINISHED'} if ok else {'CANCELLED'}


# ---------------------------------------------------------------------------
# Preferences panel
# ---------------------------------------------------------------------------

class LASImporterPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout
        laspy  = get_laspy()
        if laspy is None:
            box = layout.box()
            box.label(text="laspy is NOT installed.", icon='ERROR')
            box.label(text="LAS files will use the built-in reader (no LAZ support).")
            box.operator("las.install_laspy", icon='IMPORT')
            box.label(text="Or manually open a terminal and run:", icon='CONSOLE')
            box.label(text=f'  "{sys.executable}" -m pip install laspy[lazrs]')
            box.label(text="Then restart Blender.")
        else:
            layout.label(
                text=f"laspy {laspy.__version__} installed — LAZ support active.",
                icon='CHECKMARK',
            )


# ---------------------------------------------------------------------------
# N-panel: LiDAR Info
# ---------------------------------------------------------------------------

class LIDAR_PT_InfoPanel(bpy.types.Panel):
    """Shows LAS header metadata for the active imported point cloud object"""
    bl_label       = "LiDAR Info"
    bl_idname      = "LIDAR_PT_InfoPanel"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'LiDAR'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get('las_point_count') is not None

    def draw(self, context):
        layout = self.layout
        obj    = context.active_object

        col = layout.column(align=True)
        col.label(text=f"LAS version:      {obj.get('las_version', 'N/A')}")
        col.label(text=f"Point format:     {obj.get('las_point_format', 'N/A')}")
        col.label(text=f"Point count:      {obj.get('las_point_count', 'N/A'):,}" if isinstance(obj.get('las_point_count'), int) else f"Point count:      {obj.get('las_point_count', 'N/A')}")
        col.separator()
        col.label(text=f"Scale:            {obj.get('las_scale', 'N/A')}")
        col.label(text=f"Offset:           {obj.get('las_offset', 'N/A')}")
        col.label(text=f"Min:              {obj.get('las_min', 'N/A')}")
        col.label(text=f"Max:              {obj.get('las_max', 'N/A')}")
        col.separator()
        col.label(text=f"Creation date:    {obj.get('las_creation_date', 'N/A')}")
        col.label(text=f"GPS time type:    {obj.get('las_gps_time_type', 'N/A')}")
        col.label(text=f"Returns:          {obj.get('las_point_count_by_return', 'N/A')}")


# ---------------------------------------------------------------------------
# Main import operator
# ---------------------------------------------------------------------------

class IMPORT_OT_las(bpy.types.Operator, ImportHelper):
    """Import a LAS or LAZ point cloud file"""

    bl_idname  = "import_mesh.las"
    bl_label   = "Import LAS Point Cloud"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default="*.las;*.laz", options={'HIDDEN'})
    files: bpy.props.CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    directory: StringProperty(subtype='DIR_PATH', options={'HIDDEN'})

    import_mode: EnumProperty(
        name="Import As",
        items=[
            ('MESH',       "Mesh (vertices)",  "Each point becomes a mesh vertex"),
            ('POINTCLOUD', "Point Cloud",       "Native point cloud object (Blender 3.3+)"),
        ],
        default='MESH',
    )

    max_points: IntProperty(
        name="Max Points",
        description="Limit total imported points (0 = import all)",
        default=500_000, min=0, soft_max=5_000_000,
    )

    decimate_method: EnumProperty(
        name="Decimate Method",
        items=[
            ('UNIFORM', "Uniform stride", "Evenly-spaced subset"),
            ('RANDOM',  "Random sample",  "Random subset"),
        ],
        default='UNIFORM',
    )

    apply_offset: BoolProperty(
        name="Center at Origin",
        description="Subtract centroid so georeferenced data lands at world origin",
        default=True,
    )

    color_source: EnumProperty(
        name="Color Source",
        items=[
            ('RGB',            "RGB",            "Stored RGB values"),
            ('INTENSITY',      "Intensity",      "Greyscale from intensity"),
            ('CLASSIFICATION', "Classification", "Hue mapped from class code"),
            ('NONE',           "None",           "No vertex colors"),
        ],
        default='RGB',
    )

    intensity_as_weight: BoolProperty(
        name="Intensity → Vertex Weight",
        description="Also store intensity as a vertex group weight (mesh mode only)",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split    = True
        layout.use_property_decorate = False

        if get_laspy() is None:
            box = layout.box()
            box.label(text="laspy not found — using built-in reader.", icon='INFO')
            box.label(text="LAZ files will not work.")
            box.operator("las.install_laspy", icon='IMPORT')

        box = layout.box()
        box.label(text="Import Settings", icon='SETTINGS')
        box.prop(self, "import_mode")
        box.prop(self, "max_points")
        box.prop(self, "decimate_method")
        box.prop(self, "apply_offset")

        box2 = layout.box()
        box2.label(text="Color", icon='COLOR')
        box2.prop(self, "color_source")
        if self.color_source == 'INTENSITY':
            box2.prop(self, "intensity_as_weight")

    def execute(self, context):
        paths = (
            [os.path.join(self.directory, f.name) for f in self.files]
            if self.files else [self.filepath]
        )

        imported = 0
        for filepath in paths:
            obj_name = os.path.splitext(os.path.basename(filepath))[0]
            try:
                data = read_las_file(
                    filepath=filepath,
                    max_points=self.max_points,
                    decimate_method=self.decimate_method,
                    apply_offset=self.apply_offset,
                    color_source=self.color_source,
                    intensity_as_weight=self.intensity_as_weight,
                )
                create_blender_object(context, data, obj_name, self.import_mode)
                n      = data['point_count']
                reader = "laspy" if data['used_laspy'] else "built-in reader"
                self.report({'INFO'},
                    f"Imported '{obj_name}': {n:,} points via {reader}.")
                imported += 1
            except Exception as e:
                self.report({'ERROR'}, f"Failed to import '{obj_name}': {e}")
                traceback.print_exc()

        return {'FINISHED'} if imported else {'CANCELLED'}


# ---------------------------------------------------------------------------
# Menu + registration
# ---------------------------------------------------------------------------

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_las.bl_idname,
                         text="LAS Point Cloud (.las/.laz)")


_classes = (
    LAS_OT_install_laspy,
    LASImporterPreferences,
    LIDAR_PT_InfoPanel,
    IMPORT_OT_las,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
