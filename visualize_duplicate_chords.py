#!/usr/bin/env python3
"""
Create an interactive chord-style visualization for duplicate-detection pairs.

The script aggregates pairwise document/verse relationships into weighted
connections and writes a standalone Plotly HTML file. It is designed for public
demos where the relationship structure matters more than showing full content.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative


DEFAULT_INPUT = Path(r"D:\llm_analyzed_duplicates (1).csv")
DEFAULT_OUTPUT = Path("duplicate_relationship_chord.html")

RELATIONSHIP_LABELS = {
    "semantically_identical": "Duplicated",
    "one_doc_included": "Partial inclusion",
    "conflict_in_information": "Contradiction",
    "none_of_above": "Unrelated",
}

RELATIONSHIP_COLORS = {
    "Duplicated": "#1f9e89",
    "Partial inclusion": "#d99021",
    "Contradiction": "#c73e59",
    "Unrelated": "#8b95a1",
    "Other": "#6b7280",
}

BIBLE_BOOK_ORDER = [
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    "Joshua",
    "Judges",
    "Ruth",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    "1 Chronicles",
    "2 Chronicles",
    "Ezra",
    "Nehemiah",
    "Esther",
    "Job",
    "Psalms",
    "Proverbs",
    "Ecclesiastes",
    "Song of Solomon",
    "Isaiah",
    "Jeremiah",
    "Lamentations",
    "Ezekiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    "Matthew",
    "Mark",
    "Luke",
    "John",
    "Acts",
    "Romans",
    "1 Corinthians",
    "2 Corinthians",
    "Galatians",
    "Ephesians",
    "Philippians",
    "Colossians",
    "1 Thessalonians",
    "2 Thessalonians",
    "1 Timothy",
    "2 Timothy",
    "Titus",
    "Philemon",
    "Hebrews",
    "James",
    "1 Peter",
    "2 Peter",
    "1 John",
    "2 John",
    "3 John",
    "Jude",
    "Revelation",
]


@dataclass(frozen=True)
class NodeArc:
    label: str
    total_weight: float
    start: float
    end: float
    mid: float
    color: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize duplicate-detection relationships as a chord diagram."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input CSV path. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output HTML path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--node-level",
        choices=[
            "auto",
            "book",
            "chapter",
            "source",
            "source_book",
            "book_chapter",
            "source_chapter",
            "source_book_chapter",
            "verse",
        ],
        default="auto",
        help=(
            "How to group endpoints into chord segments. Use book for a full "
            "multi-book Bible run; auto falls back when the file has one book."
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=64,
        help="Keep the strongest N nodes by total relationship weight.",
    )
    parser.add_argument(
        "--top-links",
        type=int,
        default=450,
        help="Keep the strongest N aggregated links after node filtering.",
    )
    parser.add_argument(
        "--min-weight",
        type=float,
        default=0.0,
        help="Drop aggregated links below this summed similarity weight.",
    )
    parser.add_argument(
        "--include-unrelated",
        action="store_true",
        help="Include rows labelled none_of_above / Unrelated.",
    )
    parser.add_argument(
        "--weight-column",
        default="cross_encoder_similarity_value",
        help="Numeric column used as link weight; falls back to similarity.",
    )
    parser.add_argument(
        "--title",
        default="Bible Duplicate Detection Relationship Map",
        help="Figure title.",
    )
    parser.add_argument(
        "--plotly-js",
        choices=["inline", "cdn"],
        default="inline",
        help="Use inline for a fully standalone HTML file, or cdn for a smaller file.",
    )
    return parser.parse_args()


def require_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")


def normalized_relationship(raw_value: object) -> str:
    key = str(raw_value).strip()
    return RELATIONSHIP_LABELS.get(key, key or "Other")


def choose_weight_column(df: pd.DataFrame, requested: str) -> str:
    candidates = [requested, "cross_encoder_similarity_value", "similarity"]
    for column in candidates:
        if column in df.columns:
            numeric = pd.to_numeric(df[column], errors="coerce")
            if numeric.notna().any():
                return column
    raise ValueError("No usable numeric weight column found.")


def endpoint_label(row: pd.Series, side: int, node_level: str) -> str:
    source = str(row[f"item{side}_source"]).strip()
    book = str(row[f"item{side}_book"]).strip()
    chapter = int(row[f"item{side}_chapter"])
    verse = int(row[f"item{side}_verse"])

    if node_level == "book":
        return book
    if node_level == "chapter":
        return f"{book} {chapter}"
    if node_level == "source":
        return source.upper()
    if node_level == "source_book":
        return f"{source.upper()} | {book}"
    if node_level == "book_chapter":
        return f"{book} {chapter}"
    if node_level == "source_chapter":
        return f"{source.upper()} | {book} {chapter}"
    if node_level == "source_book_chapter":
        return f"{source.upper()} | {book} {chapter}"
    if node_level == "verse":
        return f"{source.upper()} | {book} {chapter}:{verse}"
    raise ValueError(f"Unsupported node level: {node_level}")


def choose_node_level(df: pd.DataFrame, requested: str) -> str:
    if requested != "auto":
        return requested

    books = set(df["item1_book"].dropna()).union(df["item2_book"].dropna())
    sources = set(df["item1_source"].dropna()).union(df["item2_source"].dropna())
    chapters = set(df["item1_chapter"].dropna()).union(df["item2_chapter"].dropna())

    if len(books) >= 2:
        return "book"
    if len(sources) >= 2 and len(chapters) >= 2:
        return "source_chapter"
    if len(chapters) >= 2:
        return "chapter"
    if len(sources) >= 2:
        return "source"
    return "book"


def ordered_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def build_aggregates(
    df: pd.DataFrame,
    node_level: str,
    weight_column: str,
    include_unrelated: bool,
) -> tuple[pd.DataFrame, pd.Series]:
    working = df.copy()
    working["relationship"] = working["llm_relationship_type"].map(normalized_relationship)
    working["weight"] = pd.to_numeric(working[weight_column], errors="coerce")
    working = working.dropna(subset=["weight"])
    working = working[working["weight"] > 0]

    if not include_unrelated:
        working = working[working["relationship"] != "Unrelated"]

    working["node1"] = working.apply(lambda row: endpoint_label(row, 1, node_level), axis=1)
    working["node2"] = working.apply(lambda row: endpoint_label(row, 2, node_level), axis=1)
    pairs = working.apply(lambda row: ordered_pair(row["node1"], row["node2"]), axis=1)
    working["source_node"] = [pair[0] for pair in pairs]
    working["target_node"] = [pair[1] for pair in pairs]

    grouped = (
        working.groupby(["relationship", "source_node", "target_node"], as_index=False)
        .agg(
            weight=("weight", "sum"),
            pair_count=("weight", "size"),
            avg_weight=("weight", "mean"),
            max_weight=("weight", "max"),
            examples=(
                "item1_chapter",
                lambda values: "",  # placeholder replaced below for stable groupby shape
            ),
        )
        .drop(columns=["examples"])
    )

    example_rows = (
        working.sort_values("weight", ascending=False)
        .groupby(["relationship", "source_node", "target_node"], as_index=False)
        .first()
    )
    example_rows["example"] = example_rows.apply(
        lambda row: (
            f"{row['item1_source'].upper()} {row['item1_book']} "
            f"{int(row['item1_chapter'])}:{int(row['item1_verse'])} | "
            f"{row['item2_source'].upper()} {row['item2_book']} "
            f"{int(row['item2_chapter'])}:{int(row['item2_verse'])}"
        ),
        axis=1,
    )
    grouped = grouped.merge(
        example_rows[["relationship", "source_node", "target_node", "example"]],
        on=["relationship", "source_node", "target_node"],
        how="left",
    )

    node_totals: dict[str, float] = {}
    for row in grouped.itertuples(index=False):
        node_totals[row.source_node] = node_totals.get(row.source_node, 0.0) + row.weight
        if row.target_node != row.source_node:
            node_totals[row.target_node] = node_totals.get(row.target_node, 0.0) + row.weight

    return grouped, pd.Series(node_totals, dtype=float).sort_values(ascending=False)


def sort_nodes(nodes: list[str], node_level: str) -> list[str]:
    book_index = {book: index for index, book in enumerate(BIBLE_BOOK_ORDER)}

    def parse_label(label: str) -> tuple:
        source = ""
        remainder = label
        if " | " in label:
            source, remainder = label.split(" | ", 1)

        parts = remainder.rsplit(" ", 1)
        book = parts[0]
        number = 0
        if len(parts) == 2:
            chapter_part = parts[1].split(":", 1)[0]
            if chapter_part.isdigit():
                number = int(chapter_part)

        return (source, book_index.get(book, 999), book, number, label)

    if node_level == "source":
        return sorted(nodes)
    return sorted(nodes, key=parse_label)


def make_node_arcs(node_totals: pd.Series, node_level: str) -> dict[str, NodeArc]:
    nodes = sort_nodes(node_totals.index.tolist(), node_level)
    totals = node_totals.loc[nodes]
    grand_total = float(totals.sum())
    gap = math.radians(max(1.2, min(4.0, 90.0 / max(len(nodes), 1))))
    available = 2 * math.pi - gap * len(nodes)
    palette = (
        qualitative.Safe
        + qualitative.Dark24
        + qualitative.Set3
        + qualitative.Plotly
    )

    cursor = math.pi / 2
    arcs: dict[str, NodeArc] = {}
    for index, (node, total) in enumerate(totals.items()):
        span = available * (float(total) / grand_total) if grand_total else available / len(nodes)
        start = cursor
        end = cursor - span
        mid = (start + end) / 2
        arcs[node] = NodeArc(
            label=node,
            total_weight=float(total),
            start=start,
            end=end,
            mid=mid,
            color=palette[index % len(palette)],
        )
        cursor = end - gap
    return arcs


def arc_points(start: float, end: float, radius: float = 1.0, steps: int = 64) -> tuple[list[float], list[float]]:
    angles = np.linspace(start, end, steps)
    return (radius * np.cos(angles)).tolist(), (radius * np.sin(angles)).tolist()


def bezier_points(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    steps: int = 48,
) -> tuple[list[float], list[float]]:
    t = np.linspace(0, 1, steps)
    points = (
        ((1 - t) ** 3)[:, None] * p0
        + (3 * ((1 - t) ** 2) * t)[:, None] * p1
        + (3 * (1 - t) * (t**2))[:, None] * p2
        + (t**3)[:, None] * p3
    )
    return points[:, 0].tolist(), points[:, 1].tolist()


def self_loop_points(mid: float, width: float) -> tuple[list[float], list[float]]:
    spread = max(0.08, min(0.22, width))
    a0 = mid - spread
    a3 = mid + spread
    return self_loop_points_between(a0, a3)


def self_loop_points_between(a0: float, a3: float) -> tuple[list[float], list[float]]:
    mid = (a0 + a3) / 2
    p0 = np.array([math.cos(a0), math.sin(a0)])
    p3 = np.array([math.cos(a3), math.sin(a3)])
    outward = np.array([math.cos(mid), math.sin(mid)])
    tangent = np.array([-math.sin(mid), math.cos(mid)])
    p1 = outward * 1.38 - tangent * 0.18
    p2 = outward * 1.38 + tangent * 0.18
    return bezier_points(p0, p1, p2, p3, steps=54)


def arc_angle(arc: NodeArc, fraction: float) -> float:
    bounded_fraction = min(1.0, max(0.0, fraction))
    return arc.start + (arc.end - arc.start) * bounded_fraction


def chord_points(
    left: NodeArc,
    right: NodeArc,
    left_angle: float | None = None,
    right_angle: float | None = None,
) -> tuple[list[float], list[float]]:
    left_angle = left.mid if left_angle is None else left_angle
    right_angle = right.mid if right_angle is None else right_angle

    if left.label == right.label:
        return self_loop_points_between(left_angle, right_angle)

    p0 = np.array([math.cos(left_angle), math.sin(left_angle)])
    p3 = np.array([math.cos(right_angle), math.sin(right_angle)])
    p1 = p0 * 0.22
    p2 = p3 * 0.22
    return bezier_points(p0, p1, p2, p3)


def relationship_rank(relationship: str) -> int:
    order = {
        "Duplicated": 0,
        "Partial inclusion": 1,
        "Contradiction": 2,
        "Unrelated": 3,
    }
    return order.get(relationship, 99)


def assign_link_ports(links: pd.DataFrame, arcs: dict[str, NodeArc]) -> pd.DataFrame:
    """Assign each link a separate endpoint angle on both incident node arcs."""
    padded = links.copy().reset_index(drop=True)
    padded["_link_id"] = np.arange(len(padded))

    endpoint_rows = []
    for row in padded.to_dict("records"):
        endpoint_rows.append(
            {
                "link_id": row["_link_id"],
                "side": "source",
                "node": row["source_node"],
                "other_node": row["target_node"],
                "relationship": row["relationship"],
                "weight": row["weight"],
            }
        )
        endpoint_rows.append(
            {
                "link_id": row["_link_id"],
                "side": "target",
                "node": row["target_node"],
                "other_node": row["source_node"],
                "relationship": row["relationship"],
                "weight": row["weight"],
            }
        )

    endpoints = pd.DataFrame(endpoint_rows)
    port_angles: dict[tuple[int, str], float] = {}
    for node, group in endpoints.groupby("node", sort=False):
        arc = arcs[node]
        ordered = group.copy()
        ordered["other_angle"] = ordered["other_node"].map(lambda value: arcs[value].mid)
        ordered["relationship_rank"] = ordered["relationship"].map(relationship_rank)
        ordered = ordered.sort_values(
            ["other_angle", "relationship_rank", "weight", "side"],
            ascending=[True, True, False, True],
        )

        endpoint_count = len(ordered)
        edge_margin = 0.10 if endpoint_count > 1 else 0.50
        gap = min(0.018, 0.18 / max(endpoint_count - 1, 1))
        usable = max(0.18, 1.0 - edge_margin * 2 - gap * max(endpoint_count - 1, 0))
        total_weight = float(ordered["weight"].sum())
        cursor = edge_margin

        for endpoint in ordered.itertuples(index=False):
            span = usable * (float(endpoint.weight) / total_weight) if total_weight else usable / endpoint_count
            fraction = cursor + span / 2
            port_angles[(int(endpoint.link_id), endpoint.side)] = arc_angle(arc, fraction)
            cursor += span + gap

    padded["source_angle"] = [
        port_angles[(int(link_id), "source")] for link_id in padded["_link_id"]
    ]
    padded["target_angle"] = [
        port_angles[(int(link_id), "target")] for link_id in padded["_link_id"]
    ]
    return padded.drop(columns=["_link_id"])


def scale_width(values: pd.Series, min_width: float = 1.0, max_width: float = 18.0) -> pd.Series:
    if values.empty:
        return values
    root = np.sqrt(values.astype(float))
    vmin = float(root.min())
    vmax = float(root.max())
    if math.isclose(vmin, vmax):
        return pd.Series([max(min_width + 2, 4.0)] * len(values), index=values.index)
    scaled = min_width + (root - vmin) / (vmax - vmin) * (max_width - min_width)
    return scaled


def add_arc_traces(fig: go.Figure, arcs: dict[str, NodeArc]) -> None:
    max_total = max((arc.total_weight for arc in arcs.values()), default=1.0)
    for arc in arcs.values():
        x, y = arc_points(arc.start, arc.end, radius=1.0)
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                line=dict(color=arc.color, width=18),
                hoverinfo="text",
                text=[
                    (
                        f"<b>{arc.label}</b><br>"
                        f"Total similarity: {arc.total_weight:,.2f}<br>"
                        f"Share: {arc.total_weight / max_total:.1%} of largest node"
                    )
                ]
                * len(x),
                showlegend=False,
            )
        )

        label_radius = 1.15
        label_angle = arc.mid
        rotation = math.degrees(label_angle)
        if rotation < -90 or rotation > 90:
            rotation += 180
        fig.add_annotation(
            x=label_radius * math.cos(label_angle),
            y=label_radius * math.sin(label_angle),
            text=arc.label,
            showarrow=False,
            textangle=rotation,
            font=dict(size=10, color="#26313f"),
            xanchor="center",
            yanchor="middle",
        )


def link_hover(row: pd.Series) -> str:
    return (
        f"<b>{row['relationship']}</b><br>"
        f"{row['source_node']} &harr; {row['target_node']}<br>"
        f"Pairs: {int(row['pair_count']):,}<br>"
        f"Sum similarity: {row['weight']:,.2f}<br>"
        f"Avg similarity: {row['avg_weight']:.3f}<br>"
        f"Best example: {row['example']}"
    )


def add_link_traces(
    fig: go.Figure,
    links: pd.DataFrame,
    arcs: dict[str, NodeArc],
    relationship_names: list[str],
) -> None:
    widths = scale_width(links["weight"])
    links = links.assign(width=widths.values)
    links = assign_link_ports(links, arcs)

    for relationship in relationship_names:
        visible = True
        color = RELATIONSHIP_COLORS.get(relationship, RELATIONSHIP_COLORS["Other"])
        subset = links[links["relationship"] == relationship]
        for _, row in subset.sort_values("weight", ascending=True).iterrows():
            left = arcs[row["source_node"]]
            right = arcs[row["target_node"]]
            x, y = chord_points(
                left,
                right,
                left_angle=float(row["source_angle"]),
                right_angle=float(row["target_angle"]),
            )
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    line=dict(color=color, width=float(row["width"])),
                    opacity=0.44 if relationship != "Contradiction" else 0.62,
                    hoverinfo="text",
                    text=[link_hover(row)] * len(x),
                    name=relationship,
                    legendgroup=relationship,
                    showlegend=False,
                    visible=visible,
                    meta=relationship,
                )
            )

    for relationship in relationship_names:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="lines",
                line=dict(
                    color=RELATIONSHIP_COLORS.get(relationship, RELATIONSHIP_COLORS["Other"]),
                    width=7,
                ),
                name=relationship,
                legendgroup=relationship,
                showlegend=True,
                hoverinfo="skip",
            )
        )


def relationship_buttons(fig: go.Figure, relationship_names: list[str]) -> list[dict]:
    trace_relationships = []
    for trace in fig.data:
        trace_relationships.append(trace.meta if hasattr(trace, "meta") else None)

    buttons = [
        dict(
            label="All relationships",
            method="update",
            args=[
                {"visible": [True] * len(fig.data)},
                {"title": fig.layout.title.text},
            ],
        )
    ]
    for relationship in relationship_names:
        visible = []
        for trace in fig.data:
            meta = trace.meta if hasattr(trace, "meta") else None
            if meta in relationship_names:
                visible.append(meta == relationship)
            else:
                visible.append(True)
        buttons.append(
            dict(
                label=relationship,
                method="update",
                args=[{"visible": visible}],
            )
        )
    return buttons


def filter_links(
    links: pd.DataFrame,
    node_totals: pd.Series,
    top_n: int,
    top_links: int,
    min_weight: float,
) -> tuple[pd.DataFrame, pd.Series, int, int]:
    all_node_count = len(node_totals)
    if top_n > 0 and all_node_count > top_n:
        kept_nodes = set(node_totals.head(top_n).index)
        links = links[
            links["source_node"].isin(kept_nodes) & links["target_node"].isin(kept_nodes)
        ].copy()
    else:
        kept_nodes = set(node_totals.index)

    if min_weight > 0:
        links = links[links["weight"] >= min_weight].copy()

    all_link_count = len(links)
    if top_links > 0 and len(links) > top_links:
        links = links.nlargest(top_links, "weight").copy()

    filtered_totals: dict[str, float] = {node: 0.0 for node in kept_nodes}
    for row in links.itertuples(index=False):
        filtered_totals[row.source_node] = filtered_totals.get(row.source_node, 0.0) + row.weight
        if row.target_node != row.source_node:
            filtered_totals[row.target_node] = filtered_totals.get(row.target_node, 0.0) + row.weight

    filtered_series = pd.Series(filtered_totals, dtype=float)
    filtered_series = filtered_series[filtered_series > 0].sort_values(ascending=False)
    links = links[
        links["source_node"].isin(filtered_series.index)
        & links["target_node"].isin(filtered_series.index)
    ].copy()
    return links, filtered_series, all_node_count, all_link_count


def build_figure(
    links: pd.DataFrame,
    node_totals: pd.Series,
    title: str,
    node_level: str,
    source_path: Path,
    all_node_count: int,
    all_link_count: int,
) -> go.Figure:
    arcs = make_node_arcs(node_totals, node_level)
    relationship_names = [
        name
        for name in ["Duplicated", "Partial inclusion", "Contradiction", "Unrelated"]
        if name in set(links["relationship"])
    ]
    relationship_names += sorted(
        set(links["relationship"]) - set(relationship_names)
    )

    fig = go.Figure()
    add_link_traces(fig, links, arcs, relationship_names)
    add_arc_traces(fig, arcs)

    total_pairs = int(links["pair_count"].sum())
    total_weight = float(links["weight"].sum())
    subtitle = (
        f"Grouped by {node_level.replace('_', ' ')} | "
        f"{len(node_totals):,}/{all_node_count:,} nodes | "
        f"{len(links):,}/{all_link_count:,} links | "
        f"{total_pairs:,} verse pairs | total similarity {total_weight:,.1f}"
    )

    fig.update_layout(
        title=dict(
            text=f"{title}<br><sup>{subtitle}</sup>",
            x=0.5,
            xanchor="center",
            font=dict(size=22, color="#172033"),
        ),
        width=1200,
        height=980,
        paper_bgcolor="#f6f8fb",
        plot_bgcolor="#f6f8fb",
        hovermode="closest",
        margin=dict(l=60, r=60, t=110, b=70),
        xaxis=dict(
            visible=False,
            range=[-1.42, 1.42],
            scaleanchor="y",
            scaleratio=1,
        ),
        yaxis=dict(visible=False, range=[-1.35, 1.35]),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.03,
            xanchor="center",
            x=0.5,
            font=dict(size=12),
            bgcolor="rgba(255,255,255,0.72)",
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=0.5,
                y=1.05,
                xanchor="center",
                yanchor="bottom",
                buttons=relationship_buttons(fig, relationship_names),
                bgcolor="#ffffff",
                bordercolor="#cbd5e1",
                font=dict(size=12, color="#172033"),
            )
        ],
        annotations=list(fig.layout.annotations)
        + [
            dict(
                x=0,
                y=-1.28,
                text=(
                    "Chord width is summed similarity; endpoints are padded along each arc. Hover links for relationship, "
                    "pair count, average score, and an example reference. "
                    f"Source: {source_path.name}"
                ),
                showarrow=False,
                font=dict(size=12, color="#5b6678"),
                xanchor="center",
            )
        ],
    )
    return fig


def main() -> None:
    args = parse_args()
    require_columns(
        pd.read_csv(args.input, nrows=0),
        [
            "item1_source",
            "item1_book",
            "item1_chapter",
            "item1_verse",
            "item2_source",
            "item2_book",
            "item2_chapter",
            "item2_verse",
            "llm_relationship_type",
        ],
    )

    df = pd.read_csv(args.input)
    weight_column = choose_weight_column(df, args.weight_column)
    node_level = choose_node_level(df, args.node_level)
    links, node_totals = build_aggregates(
        df=df,
        node_level=node_level,
        weight_column=weight_column,
        include_unrelated=args.include_unrelated,
    )
    links, filtered_totals, all_node_count, all_link_count = filter_links(
        links=links,
        node_totals=node_totals,
        top_n=args.top_n,
        top_links=args.top_links,
        min_weight=args.min_weight,
    )

    if links.empty or filtered_totals.empty:
        raise ValueError("No links left after filtering. Lower --min-weight or --top-n.")

    output = args.output
    if not output.is_absolute():
        output = Path.cwd() / output

    fig = build_figure(
        links=links,
        node_totals=filtered_totals,
        title=args.title,
        node_level=node_level,
        source_path=args.input,
        all_node_count=all_node_count,
        all_link_count=all_link_count,
    )
    include_plotlyjs = True if args.plotly_js == "inline" else "cdn"
    fig.write_html(output, include_plotlyjs=include_plotlyjs, full_html=True)

    relationship_summary = (
        links.groupby("relationship")
        .agg(links=("weight", "size"), pairs=("pair_count", "sum"), weight=("weight", "sum"))
        .sort_values("weight", ascending=False)
    )
    print(f"Wrote {output}")
    print(f"Node level: {node_level}")
    print(f"Weight column: {weight_column}")
    print(relationship_summary.to_string(float_format=lambda value: f"{value:,.2f}"))


if __name__ == "__main__":
    main()
