"""Generate refined vector SVG and PNG logo options for rabbit-fem.

Converts typography directly to exact vector path outlines using the
Zen Dots font from /home/lloydf/lfdev/fonts/Zen_Dots/ZenDots-Regular.ttf.
All variants are based on the feebs_tri6 mesh with diverse layouts:
- Text below the mesh (Families 4 and 7)
- Text overlaid on the mesh with halo contrast (Families 15, 18, 21)
- Hollow wireframes vs. multi-tone green and field-gradient meshes
- Distinct corner vs. midside node colors and radii
- Color palette: green, black, white, and grey
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import subprocess
from typing import Sequence

from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as MPath
from matplotlib.textpath import TextPath
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
FONTS_DIR = Path("/home/lloydf/lfdev/fonts")
ZEN_DOTS_PATH = FONTS_DIR / "Zen_Dots" / "ZenDots-Regular.ttf"

# Default paths for feebs_tri6 mesh data
CANDIDATE_DATA_DIRS = [
    SCRIPT_DIR / "rabbits" / "feebs_tri6",
    SCRIPT_DIR / "feebs_tri6",
    Path("/home/lloydf/rabbit-fem/data/rabbits/feebs_tri6"),
    Path("/home/lloydf/riley-raster/data/rabbits/feebs_tri6"),
]

OUTPUT_DIR = SCRIPT_DIR / "logo"
PNG_WEB_WIDTH = 1800
PNG_PRINT_DPI = 300


@dataclass(frozen=True)
class MeshData:
    """Container for feebs_tri6 finite element mesh data."""

    coords: np.ndarray
    connectivity: np.ndarray
    corner_indices: set[int]
    midside_indices: set[int]
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    cog_x: float
    cog_y: float


def load_feebs_tri6_mesh(data_dir: Path | None = None) -> MeshData:
    """Load feebs_tri6 coords and connectivity from CSV files."""
    chosen_dir: Path | None = None
    if data_dir is not None and data_dir.exists():
        chosen_dir = data_dir
    else:
        for candidate in CANDIDATE_DATA_DIRS:
            if (candidate / "coords.csv").exists() and (
                candidate / "connectivity.csv"
            ).exists():
                chosen_dir = candidate
                break

    if chosen_dir is None:
        raise FileNotFoundError(
            "Could not locate feebs_tri6 coords.csv and connectivity.csv"
        )

    coords_raw = np.loadtxt(chosen_dir / "coords.csv", delimiter=",")
    conn_raw = np.loadtxt(
        chosen_dir / "connectivity.csv", delimiter=",", dtype=np.int64
    )

    # Use only x and y columns
    coords = coords_raw[:, :2].astype(np.float64)

    corner_set: set[int] = set()
    for elem in conn_raw:
        for node_idx in elem[:3]:
            corner_set.add(int(node_idx))

    all_nodes = set(range(len(coords)))
    midside_set = all_nodes - corner_set

    xmin = float(coords[:, 0].min())
    xmax = float(coords[:, 0].max())
    ymin = float(coords[:, 1].min())
    ymax = float(coords[:, 1].max())

    p0 = coords[conn_raw[:, 0]]
    p1 = coords[conn_raw[:, 1]]
    p2 = coords[conn_raw[:, 2]]
    cents = (p0 + p1 + p2) / 3.0
    areas = 0.5 * np.abs(
        (p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1])
        - (p2[:, 0] - p0[:, 0]) * (p1[:, 1] - p0[:, 1])
    )
    total_area = float(np.sum(areas))
    cog_x = float(np.sum(cents[:, 0] * areas) / total_area)
    cog_y = float(np.sum(cents[:, 1] * areas) / total_area)

    return MeshData(
        coords=coords,
        connectivity=conn_raw,
        corner_indices=corner_set,
        midside_indices=midside_set,
        xmin=xmin,
        xmax=xmax,
        ymin=ymin,
        ymax=ymax,
        cog_x=cog_x,
        cog_y=cog_y,
    )


def text_to_vector_svg_path(
    text: str,
    font_path: Path,
    font_size: float,
    target_cx: float,
    target_cy: float,
) -> str:
    """Convert text string into centered SVG vector path commands."""
    if not font_path.exists():
        raise FileNotFoundError(f"Font file not found at {font_path}")

    fp = FontProperties(fname=str(font_path), size=font_size)
    tp = TextPath((0, 0), text, prop=fp)
    bbox = tp.get_extents()
    glyph_cx = (bbox.xmin + bbox.xmax) / 2.0
    glyph_cy = (bbox.ymin + bbox.ymax) / 2.0

    d_parts: list[str] = []
    v_idx = 0
    codes = tp.codes
    verts = tp.vertices

    while v_idx < len(codes):
        code = codes[v_idx]
        if code == MPath.MOVETO:
            xx = target_cx + (verts[v_idx][0] - glyph_cx)
            yy = target_cy - (verts[v_idx][1] - glyph_cy)
            d_parts.append(f"M {xx:.2f} {yy:.2f}")
            v_idx += 1
        elif code == MPath.LINETO:
            xx = target_cx + (verts[v_idx][0] - glyph_cx)
            yy = target_cy - (verts[v_idx][1] - glyph_cy)
            d_parts.append(f"L {xx:.2f} {yy:.2f}")
            v_idx += 1
        elif code == MPath.CURVE3:
            cx1 = target_cx + (verts[v_idx][0] - glyph_cx)
            cy1 = target_cy - (verts[v_idx][1] - glyph_cy)
            xx = target_cx + (verts[v_idx + 1][0] - glyph_cx)
            yy = target_cy - (verts[v_idx + 1][1] - glyph_cy)
            d_parts.append(
                f"Q {cx1:.2f} {cy1:.2f} {xx:.2f} {yy:.2f}"
            )
            v_idx += 2
        elif code == MPath.CURVE4:
            cx1 = target_cx + (verts[v_idx][0] - glyph_cx)
            cy1 = target_cy - (verts[v_idx][1] - glyph_cy)
            cx2 = target_cx + (verts[v_idx + 1][0] - glyph_cx)
            cy2 = target_cy - (verts[v_idx + 1][1] - glyph_cy)
            xx = target_cx + (verts[v_idx + 2][0] - glyph_cx)
            yy = target_cy - (verts[v_idx + 2][1] - glyph_cy)
            d_parts.append(
                f"C {cx1:.2f} {cy1:.2f} {cx2:.2f} {cy2:.2f} "
                f"{xx:.2f} {yy:.2f}"
            )
            v_idx += 3
        elif code == MPath.CLOSEPOLY:
            d_parts.append("Z")
            v_idx += 1
        else:
            v_idx += 1

    return " ".join(d_parts)


@dataclass
class LogoVariant:
    """Specification for one logo variation."""

    name: str
    layout: str  # "below", "above", "overlay", "overlay_badge", "horizontal"
    text: str = "Rabbit FEM"
    font_size: float = 46.0
    text_color: str = "#ffffff"
    text_halo_color: str | None = None
    text_halo_width: float = 0.0
    # Secondary subtitle text (e.g. for two-tier / horizontal)
    subtitle: str | None = None
    subtitle_size: float = 20.0
    subtitle_color: str = "#94a3b8"
    # Canvas
    canvas_w: int = 800
    canvas_h: int = 500
    bg_color: str = "#070b0e"
    canvas_rx: int = 0
    # Mesh placement
    mesh_target_w: float = 640.0
    mesh_center_x: float = 400.0
    mesh_center_y: float = 210.0
    # Mesh styling
    mesh_fill_mode: str = "hollow"  # "hollow", "solid", "faceted", "field"
    mesh_fill_palette: Sequence[str] = ("#064e3b", "#047857", "#059669")
    solid_fill_color: str = "#059669"
    edge_color: str = "#10b981"
    edge_width: float = 1.0
    # Nodes
    corner_node_color: str = "#22c55e"
    corner_node_radius: float = 2.6
    corner_node_stroke: str | None = "#000000"
    corner_node_stroke_w: float = 0.5
    midside_node_color: str = "#ffffff"
    midside_node_radius: float = 1.5
    midside_node_stroke: str | None = None
    midside_node_stroke_w: float = 0.0
    # Badge (for overlay_badge or pill)
    badge_bg: str = "#05080a"
    badge_stroke: str = "#10b981"
    badge_stroke_w: float = 1.5
    badge_rx: float = 12.0
    badge_pad_x: float = 28.0
    badge_pad_y: float = 14.0
    # Text position override
    text_cy_override: float | None = None
    text_cx_override: float | None = None


def render_logo_svg(variant: LogoVariant, mesh: MeshData) -> str:
    """Generate SVG XML markup for a specific logo variant."""
    # Compute mesh transform
    mesh_span_x = mesh.xmax - mesh.xmin
    mesh_span_y = mesh.ymax - mesh.ymin
    scale = variant.mesh_target_w / mesh_span_x
    mesh_render_h = mesh_span_y * scale

    # Top-left of mesh bounding box in SVG coords
    mesh_top_left_x = variant.mesh_center_x - (variant.mesh_target_w / 2.0)
    mesh_top_left_y = variant.mesh_center_y - (mesh_render_h / 2.0)

    # Map mesh coordinates to SVG space:
    # Screen X = mesh_top_left_x + (raw_x - xmin) * scale
    # Screen Y = mesh_top_left_y + (ymax - raw_y) * scale
    svg_coords = np.zeros_like(mesh.coords)
    svg_coords[:, 0] = (
        mesh_top_left_x + (mesh.coords[:, 0] - mesh.xmin) * scale
    )
    svg_coords[:, 1] = (
        mesh_top_left_y + (mesh.ymax - mesh.coords[:, 1]) * scale
    )

    mesh_svg_lines: list[str] = []

    # 1. Mesh triangles
    palette_len = len(variant.mesh_fill_palette)
    for idx, elem in enumerate(mesh.connectivity):
        p0 = svg_coords[elem[0]]
        p1 = svg_coords[elem[1]]
        p2 = svg_coords[elem[2]]

        if variant.mesh_fill_mode == "hollow":
            fill_str = "none"
        elif variant.mesh_fill_mode == "solid":
            fill_str = variant.solid_fill_color
        elif variant.mesh_fill_mode == "faceted":
            fill_str = variant.mesh_fill_palette[idx % palette_len]
        elif variant.mesh_fill_mode == "field":
            # Pseudo-stress/strain field based on normalized coords
            elem_cx = (p0[0] + p1[0] + p2[0]) / 3.0
            elem_cy = (p0[1] + p1[1] + p2[1]) / 3.0
            norm_u = (elem_cx - mesh_top_left_x) / variant.mesh_target_w
            norm_v = (elem_cy - mesh_top_left_y) / mesh_render_h
            val = 0.5 + 0.5 * math.sin(norm_u * 3.14159 * 2.5 + norm_v * 1.5)
            p_idx = int(val * (palette_len - 1))
            fill_str = variant.mesh_fill_palette[p_idx]
        else:
            fill_str = "none"

        elem_poly = (
            f'<polygon points="{p0[0]:.2f},{p0[1]:.2f} '
            f'{p1[0]:.2f},{p1[1]:.2f} {p2[0]:.2f},{p2[1]:.2f}" '
            f'fill="{fill_str}" stroke="{variant.edge_color}" '
            f'stroke-width="{variant.edge_width:.2f}" '
            f'stroke-linejoin="round" />'
        )
        mesh_svg_lines.append(f"    {elem_poly}")

    # 2. Midside nodes (drawn under corner nodes)
    for node_idx in sorted(mesh.midside_indices):
        pt = svg_coords[node_idx]
        stroke_attr = ""
        if (
            variant.midside_node_stroke
            and variant.midside_node_stroke_w > 0
        ):
            stroke_attr = (
                f' stroke="{variant.midside_node_stroke}" '
                f'stroke-width="{variant.midside_node_stroke_w:.2f}"'
            )
        circle_svg = (
            f'<circle cx="{pt[0]:.2f}" cy="{pt[1]:.2f}" '
            f'r="{variant.midside_node_radius:.2f}" '
            f'fill="{variant.midside_node_color}"{stroke_attr} />'
        )
        mesh_svg_lines.append(f"    {circle_svg}")

    # 3. Corner nodes (drawn on top)
    for node_idx in sorted(mesh.corner_indices):
        pt = svg_coords[node_idx]
        stroke_attr = ""
        if (
            variant.corner_node_stroke
            and variant.corner_node_stroke_w > 0
        ):
            stroke_attr = (
                f' stroke="{variant.corner_node_stroke}" '
                f'stroke-width="{variant.corner_node_stroke_w:.2f}"'
            )
        circle_svg = (
            f'<circle cx="{pt[0]:.2f}" cy="{pt[1]:.2f}" '
            f'r="{variant.corner_node_radius:.2f}" '
            f'fill="{variant.corner_node_color}"{stroke_attr} />'
        )
        mesh_svg_lines.append(f"    {circle_svg}")

    # 4. Determine text position
    if variant.layout == "below":
        text_cx = (
            variant.text_cx_override
            if variant.text_cx_override is not None
            else variant.mesh_center_x
        )
        text_cy = (
            variant.text_cy_override
            if variant.text_cy_override is not None
            else mesh_top_left_y + mesh_render_h + 52.0
        )
    elif variant.layout == "above":
        text_cx = (
            variant.text_cx_override
            if variant.text_cx_override is not None
            else variant.mesh_center_x
        )
        text_cy = (
            variant.text_cy_override
            if variant.text_cy_override is not None
            else mesh_top_left_y - 42.0
        )
    elif variant.layout in ("overlay", "overlay_badge"):
        # Centered over rabbit flank / cavity
        cog_screen_x = (
            mesh_top_left_x + (mesh.cog_x - mesh.xmin) * scale
        )
        cog_screen_y = (
            mesh_top_left_y + (mesh.ymax - mesh.cog_y) * scale
        )
        text_cx = (
            variant.text_cx_override
            if variant.text_cx_override is not None
            else cog_screen_x - 10.0
        )
        text_cy = (
            variant.text_cy_override
            if variant.text_cy_override is not None
            else cog_screen_y + 10.0
        )
    elif variant.layout == "horizontal":
        text_cx = (
            variant.text_cx_override
            if variant.text_cx_override is not None
            else variant.mesh_center_x + (variant.mesh_target_w / 2.0) + 180.0
        )
        text_cy = (
            variant.text_cy_override
            if variant.text_cy_override is not None
            else variant.mesh_center_y
        )
    else:
        text_cx = variant.mesh_center_x
        text_cy = variant.mesh_center_y

    text_svg_lines: list[str] = []

    # Optional badge backing for overlay_badge
    if variant.layout == "overlay_badge":
        # Estimate badge width based on font size and text length
        badge_w = (
            len(variant.text) * variant.font_size * 0.72
            + 2 * variant.badge_pad_x
        )
        badge_h = variant.font_size * 1.35 + 2 * variant.badge_pad_y
        badge_bx = text_cx - (badge_w / 2.0)
        badge_by = text_cy - (badge_h / 2.0)
        badge_rect = (
            f'<rect x="{badge_bx:.2f}" y="{badge_by:.2f}" '
            f'width="{badge_w:.2f}" height="{badge_h:.2f}" '
            f'rx="{variant.badge_rx:.2f}" fill="{variant.badge_bg}" '
            f'stroke="{variant.badge_stroke}" '
            f'stroke-width="{variant.badge_stroke_w:.2f}" />'
        )
        text_svg_lines.append(f"    {badge_rect}")

    # Generate typography vector paths
    text_path_d = text_to_vector_svg_path(
        variant.text,
        ZEN_DOTS_PATH,
        variant.font_size,
        text_cx,
        text_cy,
    )

    # Optional halo/outline behind text for contrast overlay
    if (
        variant.text_halo_color is not None
        and variant.text_halo_width > 0
    ):
        halo_svg = (
            f'<path d="{text_path_d}" fill="none" '
            f'stroke="{variant.text_halo_color}" '
            f'stroke-width="{variant.text_halo_width:.2f}" '
            f'stroke-linejoin="round" stroke-linecap="round" />'
        )
        text_svg_lines.append(f"    {halo_svg}")

    # Main text path
    main_text_svg = (
        f'<path d="{text_path_d}" fill="{variant.text_color}" />'
    )
    text_svg_lines.append(f"    {main_text_svg}")

    # Subtitle if present
    if variant.subtitle is not None:
        sub_cy = text_cy + variant.font_size * 0.75 + 16.0
        sub_path_d = text_to_vector_svg_path(
            variant.subtitle,
            ZEN_DOTS_PATH,
            variant.subtitle_size,
            text_cx,
            sub_cy,
        )
        sub_svg = (
            f'<path d="{sub_path_d}" fill="{variant.subtitle_color}" />'
        )
        text_svg_lines.append(f"    {sub_svg}")

    # Assemble entire SVG
    svg_out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {variant.canvas_w} {variant.canvas_h}" '
        f'width="{variant.canvas_w}" height="{variant.canvas_h}">',
    ]

    # Background rect
    if variant.bg_color.lower() != "none":
        rx_attr = (
            f' rx="{variant.canvas_rx}"' if variant.canvas_rx > 0 else ""
        )
        svg_out.append(
            f'  <rect width="100%" height="100%" '
            f'fill="{variant.bg_color}"{rx_attr} />'
        )

    # Add mesh and text
    svg_out.append("  <g id=\"mesh-elements\">")
    svg_out.extend(mesh_svg_lines)
    svg_out.append("  </g>")
    svg_out.append("  <g id=\"logo-typography\">")
    svg_out.extend(text_svg_lines)
    svg_out.append("  </g>")
    svg_out.append("</svg>\n")

    return "\n".join(svg_out)


def get_curated_v2_variants() -> list[LogoVariant]:
    """Define 26 targeted variations based on selected styles 4, 7, 15, 18, 21.

    Categories:
    - Family 4 (Light/Clean Themes with Text Below)
    - Family 7 (Dark/Monochrome Wireframe with Accent Nodes and Text Below)
    - Family 15 (Hollow Wireframe with High-Contrast Overlay Halo Text)
    - Family 18 (FE Field Gradient Contours with Overlay Halo Text)
    - Family 21 (Minimalist Slate/Grey Wireframes with Bold Overlay Text)
    """
    variants: list[LogoVariant] = []

    # =========================================================================
    # Family 4: Variations based on Style 4 (Light / Clean Themes, Text Below)
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v2_04a_light_forest_emerald",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#064e3b",
            canvas_w=840,
            canvas_h=490,
            bg_color="#ffffff",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="hollow",
            edge_color="#047857",
            edge_width=1.1,
            corner_node_color="#10b981",
            corner_node_radius=2.8,
            midside_node_color="#1e293b",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_04b_light_pitch_lines_lime_nodes",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#000000",
            canvas_w=840,
            canvas_h=490,
            bg_color="#ffffff",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="hollow",
            edge_color="#000000",
            edge_width=1.1,
            corner_node_color="#22c55e",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
            midside_node_stroke="#000000",
            midside_node_stroke_w=0.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_04c_light_slate_mint_softgrey",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#0f172a",
            subtitle="FINITE ELEMENT METHOD",
            subtitle_size=16.0,
            subtitle_color="#059669",
            canvas_w=840,
            canvas_h=520,
            bg_color="#f1f5f9",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=185.0,
            mesh_fill_mode="hollow",
            edge_color="#334155",
            edge_width=1.0,
            corner_node_color="#059669",
            corner_node_radius=2.8,
            midside_node_color="#64748b",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_04d_light_pale_wash_emerald",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#065f46",
            canvas_w=840,
            canvas_h=490,
            bg_color="#ffffff",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="solid",
            solid_fill_color="#ecfdf5",
            edge_color="#059669",
            edge_width=1.0,
            corner_node_color="#047857",
            corner_node_radius=2.7,
            midside_node_color="#a7f3d0",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_04e_light_graphite_minimal",
            layout="below",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#1e293b",
            canvas_w=840,
            canvas_h=490,
            bg_color="#ffffff",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="hollow",
            edge_color="#64748b",
            edge_width=1.0,
            corner_node_color="#10b981",
            corner_node_radius=2.8,
            midside_node_color="#cbd5e1",
            midside_node_radius=1.5,
        )
    )

    # =========================================================================
    # Family 7: Variations based on Style 7 (Dark / Mono Wireframe, Below)
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v2_07a_dark_pitch_electric_lime",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            canvas_w=840,
            canvas_h=490,
            bg_color="#000000",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="hollow",
            edge_color="#374151",
            edge_width=1.1,
            corner_node_color="#00ff88",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_07b_dark_slate_silver_mint",
            layout="below",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#34d399",
            subtitle="FINITE ELEMENT METHOD",
            subtitle_size=16.0,
            subtitle_color="#94a3b8",
            canvas_w=840,
            canvas_h=520,
            bg_color="#0f172a",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=185.0,
            mesh_fill_mode="hollow",
            edge_color="#94a3b8",
            edge_width=0.9,
            corner_node_color="#ffffff",
            corner_node_radius=2.7,
            midside_node_color="#34d399",
            midside_node_radius=1.7,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_07c_dark_charcoal_emerald_nodes",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            canvas_w=840,
            canvas_h=490,
            bg_color="#111827",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="hollow",
            edge_color="#475569",
            edge_width=1.0,
            corner_node_color="#10b981",
            corner_node_radius=2.8,
            midside_node_color="#9ca3af",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_07d_dark_white_wire_lime_accent",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            canvas_w=840,
            canvas_h=490,
            bg_color="#070b0e",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="hollow",
            edge_color="#f8fafc",
            edge_width=0.8,
            corner_node_color="#059669",
            corner_node_radius=2.8,
            midside_node_color="#4ade80",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_07e_dark_forest_matrix_neon",
            layout="below",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#4ade80",
            canvas_w=840,
            canvas_h=490,
            bg_color="#03140d",
            mesh_target_w=680.0,
            mesh_center_x=420.0,
            mesh_center_y=190.0,
            mesh_fill_mode="hollow",
            edge_color="#1f3b2c",
            edge_width=1.1,
            corner_node_color="#22c55e",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    # =========================================================================
    # Family 15: Variations based on Style 15 (Hollow Mesh, Overlay Halo Text)
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v2_15a_overlay_emerald_white_halo",
            layout="overlay",
            text="Rabbit FEM",
            font_size=54.0,
            text_color="#ffffff",
            text_halo_color="#05080a",
            text_halo_width=10.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#05080a",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#10b981",
            edge_width=1.2,
            corner_node_color="#4ade80",
            corner_node_radius=2.8,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_15b_overlay_slate_mint_halo",
            layout="overlay",
            text="Rabbit FEM",
            font_size=54.0,
            text_color="#ffffff",
            text_halo_color="#0f172a",
            text_halo_width=10.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#0f172a",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#34d399",
            edge_width=1.1,
            corner_node_color="#ffffff",
            corner_node_radius=2.8,
            midside_node_color="#64748b",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_15c_overlay_light_black_text_white_halo",
            layout="overlay",
            text="Rabbit FEM",
            font_size=54.0,
            text_color="#000000",
            text_halo_color="#ffffff",
            text_halo_width=12.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#10b981",
            edge_width=1.2,
            corner_node_color="#064e3b",
            corner_node_radius=2.8,
            midside_node_color="#94a3b8",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_15d_overlay_stacked_two_color_halo",
            layout="overlay",
            text="RABBIT",
            font_size=48.0,
            text_color="#ffffff",
            text_halo_color="#070b0e",
            text_halo_width=9.0,
            subtitle="FEM",
            subtitle_size=32.0,
            subtitle_color="#22c55e",
            canvas_w=820,
            canvas_h=420,
            bg_color="#070b0e",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#ffffff",
            edge_width=0.9,
            corner_node_color="#22c55e",
            corner_node_radius=2.8,
            midside_node_color="#64748b",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_15e_overlay_mint_text_charcoal_halo",
            layout="overlay",
            text="Rabbit FEM",
            font_size=54.0,
            text_color="#34d399",
            text_halo_color="#111827",
            text_halo_width=10.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#111827",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#4b5563",
            edge_width=1.1,
            corner_node_color="#34d399",
            corner_node_radius=2.8,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    # =========================================================================
    # Family 18: Variations based on Style 18 (FE Field Gradient, Overlay Halo)
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v2_18a_field_emerald_to_white",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#06090c",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#06090c",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#022c22",
                "#064e3b",
                "#047857",
                "#059669",
                "#10b981",
                "#6ee7b7",
                "#ffffff",
            ),
            edge_color="#061f18",
            edge_width=0.8,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#a7f3d0",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_18b_field_slate_to_lime",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#0b0f14",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#0b0f14",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#0f172a",
                "#1e293b",
                "#0f766e",
                "#059669",
                "#22c55e",
                "#86efac",
            ),
            edge_color="#0a121e",
            edge_width=0.8,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#86efac",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_18c_field_monochrome_to_emerald",
            layout="overlay",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#ffffff",
            text_halo_color="#111827",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#111827",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#111827",
                "#1f2937",
                "#374151",
                "#047857",
                "#059669",
                "#10b981",
            ),
            edge_color="#f8fafc",
            edge_width=0.7,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#10b981",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_18d_field_light_mint_to_forest",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#0f172a",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#f8fafc",
                "#d1fae5",
                "#6ee7b7",
                "#10b981",
                "#047857",
                "#064e3b",
            ),
            edge_color="#ffffff",
            edge_width=0.9,
            corner_node_color="#0f172a",
            corner_node_radius=2.6,
            midside_node_color="#ffffff",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_18e_field_deep_emerald_bands",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#031b14",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#031b14",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#022c22",
                "#064e3b",
                "#0f766e",
                "#10b981",
                "#34d399",
                "#a7f3d0",
            ),
            edge_color="#03140f",
            edge_width=0.8,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#6ee7b7",
            midside_node_radius=1.4,
        )
    )

    # =========================================================================
    # Family 21: Variations based on Style 21 (Minimal Wireframe, Bold Text)
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v2_21a_minimal_pitch_black_silver_lime",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#000000",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#000000",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#4b5563",
            edge_width=1.0,
            corner_node_color="#00ff88",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_21b_minimal_slate_electric_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#0f172a",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#0f172a",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#334155",
            edge_width=1.0,
            corner_node_color="#22c55e",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_21c_minimal_white_charcoal_emerald",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#0f172a",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#64748b",
            edge_width=1.0,
            corner_node_color="#059669",
            corner_node_radius=2.8,
            midside_node_color="#94a3b8",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_21d_minimal_wire_pill_accent",
            layout="overlay_badge",
            text="RABBIT FEM",
            font_size=44.0,
            text_color="#ffffff",
            canvas_w=820,
            canvas_h=420,
            bg_color="#090e12",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#475569",
            edge_width=1.0,
            corner_node_color="#10b981",
            corner_node_radius=2.8,
            midside_node_color="#ffffff",
            midside_node_radius=1.5,
            badge_bg="#05080a",
            badge_stroke="#10b981",
            badge_stroke_w=1.8,
            badge_rx=24.0,
            badge_pad_x=32.0,
            badge_pad_y=16.0,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_21e_minimal_transparent_dark_theme",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#070b0e",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="none",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#64748b",
            edge_width=1.1,
            corner_node_color="#22c55e",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v2_21f_minimal_transparent_light_theme",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#0f172a",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="none",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#1e293b",
            edge_width=1.1,
            corner_node_color="#059669",
            corner_node_radius=2.9,
            midside_node_color="#64748b",
            midside_node_radius=1.6,
        )
    )

    return variants


def get_curated_v3_variants() -> list[LogoVariant]:
    """Return ~25 v3 variations based on 18a, 18c, 18d, 21c, and 21a.

    Positioning, layout, dimensions, and text strings remain strictly
    identical to the baselines. Only colors (background, field palette,
    element edges, and node accents) are modified. Special emphasis is
    placed on 18d with black and grey element lines.
    """
    variants: list[LogoVariant] = []

    # =========================================================================
    # Family 18d: Variations based on 18d with Black & Grey Element Lines
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v3_18d_01_black_lines_slate_text",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#000000",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#f8fafc",
                "#d1fae5",
                "#6ee7b7",
                "#10b981",
                "#047857",
                "#064e3b",
            ),
            edge_color="#000000",
            edge_width=0.9,
            corner_node_color="#000000",
            corner_node_radius=2.6,
            midside_node_color="#ffffff",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18d_02_charcoal_lines_emerald_midsides",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#0f172a",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#f0fdf4",
                "#dcfce7",
                "#86efac",
                "#22c55e",
                "#15803d",
                "#14532d",
            ),
            edge_color="#1e293b",
            edge_width=0.9,
            corner_node_color="#0f172a",
            corner_node_radius=2.6,
            midside_node_color="#10b981",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18d_03_slate_lines_forest_corners",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#0f172a",
            text_halo_color="#f8fafc",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#f8fafc",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#f8fafc",
                "#d1fae5",
                "#6ee7b7",
                "#10b981",
                "#047857",
                "#064e3b",
            ),
            edge_color="#334155",
            edge_width=0.9,
            corner_node_color="#064e3b",
            corner_node_radius=2.6,
            midside_node_color="#f8fafc",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18d_04_cool_grey_lines_mint_field",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#1e293b",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#ffffff",
                "#e2e8f0",
                "#a7f3d0",
                "#34d399",
                "#059669",
                "#047857",
            ),
            edge_color="#475569",
            edge_width=0.9,
            corner_node_color="#1e293b",
            corner_node_radius=2.6,
            midside_node_color="#ffffff",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18d_05_mid_grey_lines_emerald_field",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#0f172a",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#ecfdf5",
                "#a7f3d0",
                "#34d399",
                "#10b981",
                "#047857",
                "#064e3b",
            ),
            edge_color="#64748b",
            edge_width=0.9,
            corner_node_color="#0f172a",
            corner_node_radius=2.6,
            midside_node_color="#10b981",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18d_06_silver_grey_lines_forest_palette",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#0f172a",
            text_halo_color="#f1f5f9",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#f1f5f9",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#ffffff",
                "#d1fae5",
                "#6ee7b7",
                "#10b981",
                "#059669",
                "#064e3b",
            ),
            edge_color="#64748b",
            edge_width=0.9,
            corner_node_color="#064e3b",
            corner_node_radius=2.6,
            midside_node_color="#94a3b8",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18d_07_graphite_lines_mono_to_mint",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#090e12",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#f8fafc",
                "#cbd5e1",
                "#94a3b8",
                "#34d399",
                "#10b981",
                "#065f46",
            ),
            edge_color="#1e293b",
            edge_width=0.9,
            corner_node_color="#000000",
            corner_node_radius=2.6,
            midside_node_color="#34d399",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18d_08_jet_black_lines_vivid_green",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#09090b",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#f0fdf4",
                "#bbf7d0",
                "#4ade80",
                "#22c55e",
                "#16a34a",
                "#15803d",
            ),
            edge_color="#09090b",
            edge_width=0.9,
            corner_node_color="#15803d",
            corner_node_radius=2.6,
            midside_node_color="#09090b",
            midside_node_radius=1.4,
        )
    )

    # =========================================================================
    # Family 18a: Variations based on 18a (Dark Field Canvas, "Rabbit FEM")
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v3_18a_01_pure_black_emerald_silver_lines",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#000000",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#000000",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#022c22",
                "#064e3b",
                "#047857",
                "#059669",
                "#10b981",
                "#6ee7b7",
                "#ffffff",
            ),
            edge_color="#475569",
            edge_width=0.8,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#10b981",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18a_02_charcoal_field_white_lines",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#0f172a",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#0f172a",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#0f172a",
                "#064e3b",
                "#059669",
                "#10b981",
                "#34d399",
                "#d1fae5",
            ),
            edge_color="#ffffff",
            edge_width=0.8,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#34d399",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18a_03_obsidian_mint_emerald_lines",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#040a08",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#040a08",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#041f17",
                "#064e3b",
                "#047857",
                "#10b981",
                "#34d399",
                "#ecfdf5",
            ),
            edge_color="#10b981",
            edge_width=0.8,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#a7f3d0",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18a_04_deep_grey_field_black_lines",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#18181b",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#18181b",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#18181b",
                "#064e3b",
                "#059669",
                "#10b981",
                "#6ee7b7",
                "#ffffff",
            ),
            edge_color="#000000",
            edge_width=0.8,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#000000",
            midside_node_radius=1.4,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18a_05_monochrome_bg_lime_accent_field",
            layout="overlay",
            text="Rabbit FEM",
            font_size=52.0,
            text_color="#ffffff",
            text_halo_color="#0a0f0d",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#0a0f0d",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#0f172a",
                "#1e293b",
                "#047857",
                "#10b981",
                "#22c55e",
                "#86efac",
            ),
            edge_color="#334155",
            edge_width=0.8,
            corner_node_color="#22c55e",
            corner_node_radius=2.6,
            midside_node_color="#ffffff",
            midside_node_radius=1.4,
        )
    )

    # =========================================================================
    # Family 18c: Variations based on 18c (Charcoal/Emerald, "RABBIT FEM")
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v3_18c_01_graphite_field_emerald_lines",
            layout="overlay",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#ffffff",
            text_halo_color="#111827",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#111827",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#111827",
                "#1f2937",
                "#374151",
                "#047857",
                "#059669",
                "#10b981",
            ),
            edge_color="#10b981",
            edge_width=0.7,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#34d399",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18c_02_pure_black_bg_silver_lines",
            layout="overlay",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#ffffff",
            text_halo_color="#000000",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#000000",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#09090b",
                "#18181b",
                "#27272a",
                "#059669",
                "#10b981",
                "#34d399",
            ),
            edge_color="#94a3b8",
            edge_width=0.7,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#10b981",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18c_03_slate_bg_charcoal_lines",
            layout="overlay",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#ffffff",
            text_halo_color="#1e293b",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#1e293b",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#0f172a",
                "#1e293b",
                "#334155",
                "#047857",
                "#10b981",
                "#6ee7b7",
            ),
            edge_color="#090e17",
            edge_width=0.7,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#6ee7b7",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18c_04_forest_slate_white_lines",
            layout="overlay",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#ffffff",
            text_halo_color="#0b1311",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#0b1311",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#111827",
                "#064e3b",
                "#047857",
                "#059669",
                "#10b981",
                "#a7f3d0",
            ),
            edge_color="#e2e8f0",
            edge_width=0.7,
            corner_node_color="#a7f3d0",
            corner_node_radius=2.6,
            midside_node_color="#ffffff",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_18c_05_deep_charcoal_vivid_green_field",
            layout="overlay",
            text="RABBIT FEM",
            font_size=48.0,
            text_color="#ffffff",
            text_halo_color="#18181b",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#18181b",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="field",
            mesh_fill_palette=(
                "#18181b",
                "#27272a",
                "#3f3f46",
                "#15803d",
                "#22c55e",
                "#86efac",
            ),
            edge_color="#52525b",
            edge_width=0.7,
            corner_node_color="#ffffff",
            corner_node_radius=2.6,
            midside_node_color="#22c55e",
            midside_node_radius=1.5,
        )
    )

    # =========================================================================
    # Family 21c: Variations based on 21c (Light Canvas Wire, "RABBIT FEM")
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v3_21c_01_crisp_black_wire_emerald_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#000000",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#000000",
            edge_width=1.0,
            corner_node_color="#059669",
            corner_node_radius=2.8,
            midside_node_color="#64748b",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21c_02_charcoal_wire_lime_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#0f172a",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#1e293b",
            edge_width=1.0,
            corner_node_color="#16a34a",
            corner_node_radius=2.8,
            midside_node_color="#0f172a",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21c_03_emerald_wire_black_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#047857",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#059669",
            edge_width=1.0,
            corner_node_color="#000000",
            corner_node_radius=2.8,
            midside_node_color="#94a3b8",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21c_04_soft_slate_wire_mono_green",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#0f172a",
            text_halo_color="#f8fafc",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#f8fafc",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#475569",
            edge_width=1.0,
            corner_node_color="#047857",
            corner_node_radius=2.8,
            midside_node_color="#10b981",
            midside_node_radius=1.5,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21c_05_graphite_wire_forest_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#0f172a",
            text_halo_color="#ffffff",
            text_halo_width=11.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#ffffff",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#334155",
            edge_width=1.0,
            corner_node_color="#064e3b",
            corner_node_radius=2.8,
            midside_node_color="#334155",
            midside_node_radius=1.5,
        )
    )

    # =========================================================================
    # Family 21a: Variations based on 21a (Dark Canvas Wire, "RABBIT FEM")
    # =========================================================================
    variants.append(
        LogoVariant(
            name="v3_21a_01_pitch_black_silver_wire_emerald_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#000000",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#000000",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#94a3b8",
            edge_width=1.0,
            corner_node_color="#10b981",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21a_02_charcoal_bg_emerald_wire_white_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#0f172a",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#0f172a",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#10b981",
            edge_width=1.0,
            corner_node_color="#ffffff",
            corner_node_radius=2.9,
            midside_node_color="#6ee7b7",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21a_03_obsidian_dark_grey_wire_neon_green_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#050505",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#050505",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#3f3f46",
            edge_width=1.0,
            corner_node_color="#22c55e",
            corner_node_radius=2.9,
            midside_node_color="#a1a1aa",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21a_04_deep_forest_slate_wire_white_nodes",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#06130d",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#06130d",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#475569",
            edge_width=1.0,
            corner_node_color="#34d399",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    variants.append(
        LogoVariant(
            name="v3_21a_05_pure_black_ghost_white_wire_emerald_accents",
            layout="overlay",
            text="RABBIT FEM",
            font_size=50.0,
            text_color="#ffffff",
            text_halo_color="#000000",
            text_halo_width=9.0,
            canvas_w=820,
            canvas_h=420,
            bg_color="#000000",
            mesh_target_w=720.0,
            mesh_center_x=410.0,
            mesh_center_y=210.0,
            mesh_fill_mode="hollow",
            edge_color="#ffffff",
            edge_width=0.9,
            corner_node_color="#00ff88",
            corner_node_radius=2.9,
            midside_node_color="#ffffff",
            midside_node_radius=1.6,
        )
    )

    return variants


def export_svg_to_png(svg_path: Path, png_path: Path, width: int) -> None:
    """Render an SVG to a high-resolution PNG using Inkscape CLI."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "inkscape",
            str(svg_path),
            f"--export-filename={png_path}",
            f"--export-width={width}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def generate_all_logos(
    output_dir: Path = OUTPUT_DIR,
    mesh_data_dir: Path | None = None,
    export_png: bool = True,
    version: str = "v3",
) -> None:
    """Generate curated logo variations as SVG and PNGs."""
    print("Loading feebs_tri6 mesh data...")
    mesh = load_feebs_tri6_mesh(mesh_data_dir)
    print(
        f"Mesh loaded: {len(mesh.coords)} nodes ({len(mesh.corner_indices)} "
        f"corners, {len(mesh.midside_indices)} midsides), "
        f"{len(mesh.connectivity)} tri6 elements."
    )

    if version == "v2":
        ver_dir = output_dir / "v2"
        variants = get_curated_v2_variants()
    else:
        ver_dir = output_dir / "v3"
        variants = get_curated_v3_variants()

    ver_svg_dir = ver_dir / "svg"
    ver_png_dir = ver_dir / "png"

    ver_svg_dir.mkdir(parents=True, exist_ok=True)
    if export_png:
        ver_png_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Generating {len(variants)} curated {version} logo variations "
        f"in {ver_dir} and {output_dir}..."
    )

    for idx, var in enumerate(variants, start=1):
        svg_content = render_logo_svg(var, mesh)

        # Write to version/svg and version root
        svg_file = ver_svg_dir / f"{var.name}.svg"
        svg_file.write_text(svg_content, encoding="utf-8")
        direct_svg = ver_dir / f"{var.name}.svg"
        direct_svg.write_text(svg_content, encoding="utf-8")

        # Also write to top-level logo dir
        top_svg = output_dir / f"{var.name}.svg"
        top_svg.write_text(svg_content, encoding="utf-8")

        if export_png:
            png_file = ver_png_dir / f"{var.name}.png"
            export_svg_to_png(svg_file, png_file, width=PNG_WEB_WIDTH)

            direct_png = ver_dir / f"{var.name}.png"
            export_svg_to_png(svg_file, direct_png, width=PNG_WEB_WIDTH)

            top_png = output_dir / f"{var.name}.png"
            export_svg_to_png(svg_file, top_png, width=PNG_WEB_WIDTH)

        print(f"  [{idx:02d}/{len(variants)}] {var.name}")

    print(f"\nAll {len(variants)} {version} logos successfully generated!")
    print(f"  {version.upper()} SVGs: {ver_svg_dir}")
    if export_png:
        print(
            f"  {version.upper()} PNGs: {ver_png_dir} "
            f"(width: {PNG_WEB_WIDTH}px)"
        )


if __name__ == "__main__":
    generate_all_logos(version="v3")
