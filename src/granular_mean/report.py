from __future__ import annotations

import base64
import html
import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from granular_mean.cases import PHASES_PER_CYCLE
from granular_mean.metrics import top_height_field
from granular_mean.trajectory import Trajectory


def _representative_frames(
    case_id: str,
    trajectory: Trajectory,
    order: dict[str, np.ndarray],
) -> list[int]:
    if case_id == "e":
        return [int(np.argmin(order["contrast"][:-1]))]
    symmetry = {
        "a": "q4",
        "b": "q2",
        "cd": "q6",
        "f": "q4",
        "g": "q2",
        "h": "q6",
    }[case_id]
    score = order["contrast"][:-1] * order[symmetry][:-1]
    first = int(np.argmax(score))
    if case_id != "cd":
        return [first]
    second = first + PHASES_PER_CYCLE
    if second >= trajectory.frame_count - 1:
        second = first - PHASES_PER_CYCLE
    return [first, second]


def _encode_field(
    field: np.ndarray,
    *,
    low: float,
    high: float,
) -> str:
    if high <= low:
        high = low + 1.0
    scaled = np.clip((field - low) / (high - low), 0.0, 1.0)
    pixels = np.rint(255.0 * scaled).astype(np.uint8)
    image = Image.fromarray(pixels).resize(
        (320, 320),
        Image.Resampling.NEAREST,
    )
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    encoded = base64.b64encode(stream.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def representative_images(
    case_id: str,
    reference: Trajectory,
    candidate: Trajectory,
    reference_order: dict[str, np.ndarray],
    shift_cycles: int,
    reference_box_width: float,
    candidate_box_width: float,
) -> list[dict[str, object]]:
    images = []
    shift_frames = shift_cycles * PHASES_PER_CYCLE
    candidate_core = candidate.frame_count - 1
    for reference_frame in _representative_frames(
        case_id,
        reference,
        reference_order,
    ):
        candidate_frame = (
            reference_frame + shift_frames
        ) % candidate_core
        reference_field = top_height_field(
            reference.positions[reference_frame],
            reference.diameters,
            float(reference.plate_z[reference_frame]),
            reference_box_width,
        )
        candidate_field = top_height_field(
            candidate.positions[candidate_frame],
            candidate.diameters,
            float(candidate.plate_z[candidate_frame]),
            candidate_box_width,
        )
        combined = np.concatenate(
            (reference_field.ravel(), candidate_field.ravel())
        )
        low, high = np.percentile(combined, (2, 98))
        images.append(
            {
                "reference_frame": reference_frame,
                "candidate_frame": candidate_frame,
                "drive_phase": float(
                    reference.drive_phase[reference_frame]
                ),
                "reference": _encode_field(
                    reference_field,
                    low=float(low),
                    high=float(high),
                ),
                "candidate": _encode_field(
                    candidate_field,
                    low=float(low),
                    high=float(high),
                ),
            }
        )
    return images


def _number(value: object, digits: int = 4) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}g}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def render_comparison_report(
    details: dict[str, Any],
    images: dict[str, list[dict[str, object]]],
) -> str:
    case_sections = []
    for case_id, case in details["cases"].items():
        pattern = html.escape(str(case["paper_consistency"]["expected_pattern"]))
        pattern_errors = case["updated_c_fidelity"]["errors"]
        candidate_means = case["updated_c_fidelity"][
            "candidate_cycle_means"
        ]
        paper_differences = case["paper_consistency"].get(
            "absolute_differences",
            {},
        )
        metric_rows = "".join(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{_number(candidate_means[name])}</td>"
            f"<td>{_number(pattern_errors[name]['normalized_rmse'])}</td>"
            f"<td>{_number(paper_differences.get(name))}</td>"
            "</tr>"
            for name in (
                "contrast",
                "dominant_wavelength",
                "q2",
                "q4",
                "q6",
            )
        )
        image_rows = "".join(
            "<div class='pair'>"
            "<figure>"
            f"<img src='{item['reference']}' alt='Updated-C reference {case_id}'>"
            "<figcaption>Updated-C reference</figcaption>"
            "</figure>"
            "<figure>"
            f"<img src='{item['candidate']}' alt='Candidate {case_id}'>"
            "<figcaption>Candidate</figcaption>"
            "</figure>"
            f"<p>drive phase {_number(item['drive_phase'], 3)}</p>"
            "</div>"
            for item in images.get(case_id, ())
        )
        simulation = case["simulation"]
        case_sections.append(
            "<section>"
            f"<h2>{html.escape(case_id)} <span>{pattern}</span></h2>"
            "<div class='facts'>"
            f"<b>Cycles compared</b> {simulation['comparison_cycles']}"
            f"<b>Candidate particles</b> {simulation['candidate_particle_count']}"
            f"<b>Cycle shift</b> {case['alignment']['integer_drive_cycle_shift']}"
            f"<b>Alignment NRMSE</b> {_number(case['alignment']['normalized_rmse'])}"
            "</div>"
            f"<div class='images'>{image_rows}</div>"
            "<table>"
            "<thead><tr><th>Metric</th><th>Candidate mean</th>"
            "<th>Updated-C NRMSE</th><th>Paper absolute difference</th>"
            "</tr></thead>"
            f"<tbody>{metric_rows}</tbody>"
            "</table>"
            "</section>"
        )

    complete = details["contract_completion"]["complete"]
    status = "complete" if complete else "incomplete"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Granular Figure 1 comparison</title>"
        "<style>"
        ":root{--ink:#17231c;--paper:#f3efe3;--accent:#d5522b;"
        "--line:#c9c1ae;--panel:#fffdf7}"
        "*{box-sizing:border-box}body{margin:0;background:var(--paper);"
        "color:var(--ink);font-family:Georgia,'Times New Roman',serif}"
        "main{max-width:1180px;margin:auto;padding:48px 24px 80px}"
        "header{border-bottom:4px solid var(--ink);padding-bottom:24px}"
        "h1{font-size:clamp(2.2rem,6vw,5rem);line-height:.92;margin:0 0 18px}"
        "header p{font-family:'Courier New',monospace;margin:5px 0}"
        "section{background:var(--panel);margin-top:28px;padding:24px;"
        "border:1px solid var(--line);box-shadow:7px 7px 0 #d8d0bd}"
        "h2{font-size:2rem;margin:0 0 18px;text-transform:uppercase}"
        "h2 span{font:italic 1rem Georgia;text-transform:none;color:var(--accent)}"
        ".facts{display:grid;grid-template-columns:auto 1fr auto 1fr;"
        "gap:8px 14px;font-family:'Courier New',monospace;font-size:.86rem}"
        ".images{display:flex;gap:20px;flex-wrap:wrap;margin:22px 0}"
        ".pair{display:grid;grid-template-columns:1fr 1fr;gap:10px;"
        "max-width:680px}.pair p{grid-column:1/-1;margin:0;font-size:.8rem}"
        "figure{margin:0}img{display:block;width:100%;image-rendering:pixelated;"
        "border:1px solid var(--ink)}figcaption{font-size:.78rem;margin-top:5px}"
        "table{width:100%;border-collapse:collapse;font-size:.88rem}"
        "th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line)}"
        "th{font-family:'Courier New',monospace}"
        "@media(max-width:700px){.facts{grid-template-columns:auto 1fr}"
        ".pair{grid-template-columns:1fr}table{display:block;overflow:auto}}"
        "</style></head><body><main><header>"
        "<h1>Granular Figure 1 comparison</h1>"
        f"<p>submission contract: {status}</p>"
        f"<p>overlap checks: {str(details['include_overlaps']).lower()}</p>"
        "<p>Height maps use a shared reference/candidate scale; white is higher.</p>"
        "</header>"
        + "".join(case_sections)
        + "</main></body></html>"
    )


def write_comparison_report(
    details: dict[str, Any],
    images: dict[str, list[dict[str, object]]],
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_comparison_report(details, images))
