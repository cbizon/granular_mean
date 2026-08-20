from __future__ import annotations

import base64
import html
import io
import json
import math
import re
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


def _series(
    values: object,
    *,
    component: int | None = None,
) -> list[float]:
    array = np.asarray(values, dtype=np.float64)
    if component is not None:
        if array.ndim != 2 or array.shape[1] <= component:
            raise ValueError(
                f"expected vector series with component {component}"
            )
        array = array[:, component]
    if array.ndim != 1 or not array.size:
        raise ValueError("chart series must be a nonempty vector")
    if not np.all(np.isfinite(array)):
        raise ValueError("chart series must contain only finite values")
    return array.tolist()


def _comparison_series(
    comparison: dict[str, Any],
    name: str,
    *,
    component: int | None = None,
) -> tuple[list[float], list[float]]:
    return (
        _series(
            comparison["reference_phase_conditioned"][name],
            component=component,
        ),
        _series(
            comparison["candidate_phase_conditioned"][name],
            component=component,
        ),
    )


def _closed_phase_series(values: list[float]) -> list[float]:
    return [*values, values[0]]


def _line_path(
    values: list[float],
    *,
    width: int,
    height: int,
    left: int,
    right: int,
    top: int,
    bottom: int,
    y_min: float,
    y_max: float,
    log_scale: bool,
) -> str:
    transformed = (
        [math.log1p(max(0.0, value)) for value in values]
        if log_scale
        else values
    )
    transformed_min = (
        math.log1p(max(0.0, y_min))
        if log_scale
        else y_min
    )
    transformed_max = (
        math.log1p(max(0.0, y_max))
        if log_scale
        else y_max
    )
    x_span = width - left - right
    y_span = height - top - bottom
    denominator = max(1, len(values) - 1)
    value_span = max(1e-12, transformed_max - transformed_min)
    points = []
    for index, value in enumerate(transformed):
        x = left + (index / denominator) * x_span
        y = (
            height
            - bottom
            - ((value - transformed_min) / value_span) * y_span
        )
        points.append(
            f"{'M' if index == 0 else 'L'}{x:.2f},{y:.2f}"
        )
    return " ".join(points)


def _line_chart(
    title: str,
    reference: list[float],
    candidate: list[float],
    *,
    note: str = "",
    log_scale: bool = False,
) -> str:
    if len(reference) != len(candidate):
        raise ValueError(f"chart series length mismatch for {title}")
    reference = _closed_phase_series(reference)
    candidate = _closed_phase_series(candidate)
    values = [*reference, *candidate]
    y_min = min(values)
    y_max = max(values)
    if log_scale:
        y_min = 0.0
    elif y_min == y_max:
        y_min -= 1.0
        y_max += 1.0
    else:
        padding = (y_max - y_min) * 0.06
        y_min -= padding
        y_max += padding
    if y_min == y_max:
        y_max = y_min + 1.0

    width = 450
    height = 225
    left = 62
    right = 16
    top = 16
    bottom = 42
    transformed_min = (
        math.log1p(max(0.0, y_min))
        if log_scale
        else y_min
    )
    transformed_max = (
        math.log1p(max(0.0, y_max))
        if log_scale
        else y_max
    )
    ticks = []
    for fraction in (0.0, 0.5, 1.0):
        y = top + fraction * (height - top - bottom)
        transformed_value = (
            transformed_max
            - fraction * (transformed_max - transformed_min)
        )
        value = (
            math.expm1(transformed_value)
            if log_scale
            else transformed_value
        )
        ticks.append((y, value))
    reference_path = _line_path(
        reference,
        width=width,
        height=height,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        y_min=y_min,
        y_max=y_max,
        log_scale=log_scale,
    )
    candidate_path = _line_path(
        candidate,
        width=width,
        height=height,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        y_min=y_min,
        y_max=y_max,
        log_scale=log_scale,
    )
    grid = "".join(
        "<line class='grid-line' "
        f"x1='{left}' x2='{width - right}' y1='{y:.2f}' y2='{y:.2f}'/>"
        "<text class='axis-label' "
        f"x='{left - 7}' y='{y + 4:.2f}' text-anchor='end'>"
        f"{_number(value, 3)}</text>"
        for y, value in ticks
    )
    return (
        "<figure class='chart'>"
        f"<figcaption><strong>{html.escape(title)}</strong>"
        f"<span>{html.escape(note)}</span></figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' "
        f"aria-label='{html.escape(title)} reference and candidate comparison'>"
        f"{grid}"
        f"<path class='reference-line' d='{reference_path}'/>"
        f"<path class='candidate-line' d='{candidate_path}'/>"
        f"<text class='axis-label' x='{left}' y='{height - 12}' "
        "text-anchor='middle'>0</text>"
        f"<text class='axis-label' x='{width - right}' y='{height - 12}' "
        "text-anchor='middle'>1</text>"
        f"<text class='axis-label' x='{(left + width - right) / 2:.2f}' "
        f"y='{height - 12}' text-anchor='middle'>drive phase</text>"
        "</svg></figure>"
    )


def _total_bar_chart(
    title: str,
    columns: list[str],
    reference: list[float],
    candidate: list[float],
    *,
    note: str,
) -> str:
    if not (len(columns) == len(reference) == len(candidate) and columns):
        raise ValueError(f"bar chart shape mismatch for {title}")
    values = [*reference, *candidate]
    if any(value < 0 or not math.isfinite(value) for value in values):
        raise ValueError(
            f"bar chart values must be finite and nonnegative: {title}"
        )
    width = 450
    height = 225
    left = 62
    right = 16
    top = 16
    bottom = 56
    transformed_max = math.log1p(max([1.0, *values]))
    plot_width = width - left - right
    group_width = plot_width / len(columns)
    bar_width = min(34.0, group_width * 0.28)

    def bar_y(value: float) -> float:
        return (
            height
            - bottom
            - (math.log1p(value) / transformed_max)
            * (height - top - bottom)
        )

    ticks = []
    for fraction in (0.0, 0.5, 1.0):
        y = top + fraction * (height - top - bottom)
        value = math.expm1(transformed_max * (1.0 - fraction))
        ticks.append((y, value))
    grid = "".join(
        "<line class='grid-line' "
        f"x1='{left}' x2='{width - right}' y1='{y:.2f}' y2='{y:.2f}'/>"
        "<text class='axis-label' "
        f"x='{left - 7}' y='{y + 4:.2f}' text-anchor='end'>"
        f"{_number(value, 3)}</text>"
        for y, value in ticks
    )
    bars = []
    for index, column in enumerate(columns):
        center = left + group_width * (index + 0.5)
        reference_y = bar_y(reference[index])
        candidate_y = bar_y(candidate[index])
        bars.extend(
            (
                "<rect class='bar-reference' "
                f"x='{center - bar_width - 2:.2f}' y='{reference_y:.2f}' "
                f"width='{bar_width:.2f}' "
                f"height='{height - bottom - reference_y:.2f}'/>",
                "<rect class='bar-candidate' "
                f"x='{center + 2:.2f}' y='{candidate_y:.2f}' "
                f"width='{bar_width:.2f}' "
                f"height='{height - bottom - candidate_y:.2f}'/>",
                "<text class='axis-label' "
                f"x='{center:.2f}' y='{height - 29}' text-anchor='middle'>"
                f"{html.escape(column.replace('_', ' '))}</text>",
            )
        )
    return (
        "<figure class='chart'>"
        f"<figcaption><strong>{html.escape(title)}</strong>"
        f"<span>{html.escape(note)}</span></figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' "
        f"aria-label='{html.escape(title)} reference and candidate comparison'>"
        f"{grid}{''.join(bars)}</svg></figure>"
    )


def _matrix_column(values: object, index: int) -> list[float]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] <= index:
        raise ValueError(f"expected matrix series with column {index}")
    return _series(array[:, index])


def _diagnostic_charts(case: dict[str, Any]) -> str:
    scalar = case["scalar_dynamics"]
    rotational = case["rotational_dynamics"]
    scalar_specs = (
        ("Center-of-mass height", "com_height", None),
        ("Layer depth", "layer_depth", None),
        ("RMS speed", "rms_velocity", None),
        ("Mean vertical velocity", "mean_velocity", 2),
    )
    rotational_specs = (
        ("Mean vertical spin", "mean_spin", 2),
        ("RMS spin", "rms_spin", None),
        (
            "Rotational kinetic energy",
            "rotational_kinetic_energy",
            None,
        ),
    )
    scalar_charts = "".join(
        _line_chart(
            title,
            *_comparison_series(
                scalar,
                name,
                component=component,
            ),
        )
        for title, name, component in scalar_specs
    )
    rotational_charts = "".join(
        _line_chart(
            title,
            *_comparison_series(
                rotational,
                name,
                component=component,
            ),
        )
        for title, name, component in rotational_specs
    )

    collisions = case["collision_rates"]
    collision_columns = list(collisions["columns"])
    collision_reference_total = _series(collisions["reference"]["total"])
    collision_candidate_total = _series(collisions["candidate"]["total"])
    collision_charts = _total_bar_chart(
        "Collision rates per particle per cycle",
        collision_columns,
        collision_reference_total,
        collision_candidate_total,
        note="log1p scale",
    )
    for index, column in enumerate(collision_columns):
        collision_charts += _line_chart(
            f"{column.replace('_', ' ').title()} collision rate",
            _matrix_column(
                collisions["reference"]["phase_conditioned"],
                index,
            ),
            _matrix_column(
                collisions["candidate"]["phase_conditioned"],
                index,
            ),
            note="phase-conditioned · log1p scale",
            log_scale=True,
        )

    overlap_charts = ""
    overlaps = case.get("overlaps")
    if overlaps is not None:
        overlap_columns = list(overlaps["columns"])
        overlap_charts = _total_bar_chart(
            "Total overlap counts",
            overlap_columns,
            _series(overlaps["reference_total"]),
            _series(overlaps["candidate_total"]),
            note="log1p scale",
        )
        for index, column in enumerate(overlap_columns):
            overlap_charts += _line_chart(
                f"{column.replace('_', ' ').title()} overlaps",
                _matrix_column(
                    overlaps["reference_phase_conditioned"],
                    index,
                ),
                _matrix_column(
                    overlaps["candidate_phase_conditioned"],
                    index,
                ),
                note="mean count per frame · log1p scale",
                log_scale=True,
            )

    overlap_section = (
        "<h3>Overlap diagnostics</h3>"
        f"<div class='chart-grid'>{overlap_charts}</div>"
        if overlap_charts
        else ""
    )
    return (
        "<div class='diagnostics'>"
        "<div class='diagnostic-heading'>"
        "<h3>Phase-conditioned physical dynamics</h3>"
        "<div class='legend'><span class='reference-key'>Updated C</span>"
        "<span class='candidate-key'>Candidate</span></div></div>"
        f"<div class='chart-grid'>{scalar_charts}</div>"
        "<h3>Phase-conditioned rotational dynamics</h3>"
        f"<div class='chart-grid'>{rotational_charts}</div>"
        "<h3>Collision diagnostics</h3>"
        f"<div class='chart-grid'>{collision_charts}</div>"
        f"{overlap_section}</div>"
    )


def render_comparison_report(
    details: dict[str, Any],
    images: dict[str, list[dict[str, object]]],
) -> str:
    case_sections = []
    for case_id, case in details["cases"].items():
        if case.get("status") == "failed":
            error = case["error"]
            case_sections.append(
                "<section class='failed-case'>"
                f"<h2>{html.escape(case_id)} <span>not evaluated</span></h2>"
                f"<p><b>{html.escape(str(error['type']))}</b>: "
                f"{html.escape(str(error['message']))}</p>"
                "</section>"
            )
            continue
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
            f"{_diagnostic_charts(case)}"
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
        ".diagnostics{margin-top:28px;border-top:3px solid var(--ink);padding-top:22px}"
        ".diagnostics h3{margin:26px 0 12px;font-size:1.2rem;text-transform:uppercase}"
        ".diagnostic-heading{display:flex;justify-content:space-between;gap:16px;"
        "align-items:baseline}.diagnostic-heading h3{margin-top:0}"
        ".legend{display:flex;gap:16px;font:700 .76rem 'Courier New',monospace}"
        ".legend span:before{content:'';display:inline-block;width:22px;height:3px;"
        "margin-right:6px;vertical-align:middle}"
        ".reference-key:before{background:#17231c}.candidate-key:before{background:#d5522b}"
        ".chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));"
        "gap:14px}.chart{margin:0;padding:12px;background:#f8f4e8;"
        "border:1px solid var(--line)}.chart figcaption{display:flex;"
        "justify-content:space-between;gap:12px;min-height:28px}"
        ".chart figcaption span{font:italic .72rem Georgia;color:#6b665b}"
        ".chart svg{display:block;width:100%;height:auto;overflow:visible}"
        ".grid-line{stroke:#d8d0bd;stroke-width:1}.axis-label{fill:#625e55;"
        "font:10px 'Courier New',monospace}.reference-line,.candidate-line{fill:none;"
        "stroke-width:2.5;vector-effect:non-scaling-stroke}.reference-line{stroke:#17231c}"
        ".candidate-line{stroke:#d5522b}.bar-reference{fill:#17231c}"
        ".bar-candidate{fill:#d5522b}"
        ".failed-case{border-color:#a22}.failed-case p{font-family:"
        "'Courier New',monospace;color:#7d1717}"
        "@media(max-width:700px){.facts{grid-template-columns:auto 1fr}"
        ".pair{grid-template-columns:1fr}table{display:block;overflow:auto}"
        ".chart-grid{grid-template-columns:1fr}.diagnostic-heading{display:block}}"
        "</style></head><body><main><header>"
        "<h1>Granular Figure 1 comparison</h1>"
        f"<p>submission contract: {status}</p>"
        f"<p>overlap checks: {str(details['include_overlaps']).lower()}</p>"
        "<p>Height maps use a shared reference/candidate scale; white is higher.</p>"
        + (
            "<p><b>Candidate collection error:</b> "
            + html.escape(str(details["collection_error"]["message"]))
            + "</p>"
            if details.get("collection_error")
            else ""
        )
        +
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


_ARCHIVED_IMAGE_PATTERN = re.compile(
    r"<div class='pair'><figure><img src='(?P<reference>[^']+)' "
    r"alt='Updated-C reference (?P<case>[^']+)'>.*?"
    r"<img src='(?P<candidate>[^']+)' alt='Candidate (?P=case)'>.*?"
    r"<p>drive phase (?P<phase>[^<]+)</p></div>",
    re.DOTALL,
)


def rewrite_archived_comparison_report(
    details_path: Path,
    report_path: Path,
    output_path: Path | None = None,
) -> Path:
    details = json.loads(details_path.read_text())
    archived = report_path.read_text()
    images: dict[str, list[dict[str, object]]] = {
        case_id: []
        for case_id in details["cases"]
    }
    for match in _ARCHIVED_IMAGE_PATTERN.finditer(archived):
        images[match.group("case")].append(
            {
                "reference": match.group("reference"),
                "candidate": match.group("candidate"),
                "drive_phase": float(match.group("phase")),
            }
        )
    missing = [
        case_id
        for case_id, case_images in images.items()
        if details["cases"][case_id].get("status") != "failed"
        and not case_images
    ]
    if missing:
        raise ValueError(
            "archived report is missing representative images for: "
            + ", ".join(missing)
        )
    output = output_path or report_path.with_name(
        "comparison-physical.html"
    )
    if output.resolve() == report_path.resolve():
        raise ValueError("archived comparison reports must not be overwritten")
    write_comparison_report(details, images, output)
    return output
