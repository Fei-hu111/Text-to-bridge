"""Deterministic design state and response estimates for V3."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from bridge_fem_agent.rigid_frame.schema import RigidFrameInput


@dataclass(frozen=True)
class SectionControl:
    pier_height_m: float
    midspan_height_m: float
    deck_width_m: float
    web_thickness_m: float
    bottom_slab_thickness_m: float
    top_slab_thickness_m: float


@dataclass(frozen=True)
class TendonGroup:
    name: str
    role: str
    count: int
    area_each_m2: float
    jacking_stress_pa: float
    start_x_m: float
    end_x_m: float
    eccentricity_m: float

    @property
    def total_force_n(self) -> float:
        return self.count * self.area_each_m2 * self.jacking_stress_pa


@dataclass(frozen=True)
class ResponseEstimate:
    max_deflection_m: float
    deflection_limit_m: float
    deflection_ratio: float
    max_compressive_stress_pa: float
    max_tensile_stress_pa: float
    reaction_balance_error: float
    status: str
    governing_messages: list[str]


@dataclass(frozen=True)
class RigidFrameDesign:
    iteration: int
    section: SectionControl
    tendon_groups: list[TendonGroup]
    response: ResponseEstimate | None = None
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RigidFrameDesignFactory:
    """Create an initial variable-section/prestress design from span rules."""

    def create_initial(self, task: RigidFrameInput) -> RigidFrameDesign:
        main_span = task.main_span_m
        pier_height = main_span / 17.0
        midspan_height = main_span / 50.0
        section = SectionControl(
            pier_height_m=pier_height,
            midspan_height_m=midspan_height,
            deck_width_m=task.deck_width_m,
            web_thickness_m=max(0.45, task.deck_width_m / 26.0),
            bottom_slab_thickness_m=max(0.32, main_span / 500.0),
            top_slab_thickness_m=max(0.28, main_span / 600.0),
        )
        tendon_area = 2.66e-3
        x1, x2 = task.pier_stations_m
        tendons = [
            TendonGroup("Tendon-Pier01-Top", "pier_top_negative_moment", max(8, int(main_span / 18)), tendon_area, task.materials.tendon_jacking_stress_pa, x1 - task.side_span_left_m * 0.45, x1 + main_span * 0.35, 0.42 * pier_height),
            TendonGroup("Tendon-Pier02-Top", "pier_top_negative_moment", max(8, int(main_span / 18)), tendon_area, task.materials.tendon_jacking_stress_pa, x2 - main_span * 0.35, x2 + task.side_span_right_m * 0.45, 0.42 * pier_height),
            TendonGroup("Tendon-Midspan-Bottom", "midspan_positive_moment", max(10, int(main_span / 14)), tendon_area, task.materials.tendon_jacking_stress_pa, x1 + main_span * 0.18, x2 - main_span * 0.18, -0.42 * midspan_height),
            TendonGroup("Tendon-SideSpan-Bottom", "side_span_positive_moment", max(6, int((task.side_span_left_m + task.side_span_right_m) / 28)), tendon_area, task.materials.tendon_jacking_stress_pa, 0.08 * task.total_length_m, 0.92 * task.total_length_m, -0.36 * midspan_height),
        ]
        return RigidFrameDesign(iteration=0, section=section, tendon_groups=tendons, actions=["Created initial rigid-frame design from span-based rules."])


class RigidFrameResponseEvaluator:
    """Fast engineering response estimate used for deterministic optimization."""

    def evaluate(self, task: RigidFrameInput, design: RigidFrameDesign) -> ResponseEstimate:
        section = design.section
        main_span = task.main_span_m
        e_mod = task.materials.girder_elastic_modulus_pa
        avg_height = 0.55 * section.pier_height_m + 0.45 * section.midspan_height_m
        area, inertia = equivalent_box_properties(section, avg_height)
        c = avg_height / 2.0

        self_weight = task.materials.concrete_density_kg_m3 * 9.81 * area
        service_line_load = (task.roadway_load_pa + task.human_load_pa + task.second_dead_load_pa) * task.deck_width_m
        total_line_load = self_weight + service_line_load

        prestress_top = sum(group.total_force_n * abs(group.eccentricity_m) for group in design.tendon_groups if "pier_top" in group.role)
        prestress_bottom = sum(group.total_force_n * abs(group.eccentricity_m) for group in design.tendon_groups if "positive" in group.role)
        prestress_moment = 0.85 * prestress_top + 1.10 * prestress_bottom

        # Continuous rigid-frame action redistributes a large part of the simple
        # span moment into pier negative moment regions. This coefficient is
        # intentionally deterministic and can later be replaced by an LLM/tool
        # backed calibration stage.
        # TODO: expose a future LLM-assisted calibration hook using verified
        # sample-model responses as prior data.
        load_moment = total_line_load * main_span**2 / 14.0
        net_moment = max(load_moment - prestress_moment, 0.25 * load_moment)
        raw_deflection = 0.32 * 5.0 * total_line_load * main_span**4 / (384.0 * e_mod * inertia)
        prestress_deflection_reduction = min(0.65, prestress_moment / max(load_moment, 1.0) * 0.48)
        max_deflection = raw_deflection * (1.0 - prestress_deflection_reduction)
        deflection_limit = main_span / task.targets.max_deflection_ratio

        axial_prestress = sum(group.total_force_n for group in design.tendon_groups) / max(area, 1.0)
        bending_stress = net_moment * c / max(inertia, 1.0e-9)
        max_compressive = axial_prestress + 0.72 * bending_stress
        max_tensile = max(0.0, bending_stress - 1.30 * axial_prestress)
        compressive_limit = task.targets.max_compressive_stress_pa
        tensile_limit = task.targets.max_tensile_stress_pa

        messages: list[str] = []
        if max_deflection > deflection_limit:
            messages.append("Deflection exceeds target limit.")
        if max_compressive > compressive_limit:
            messages.append("Compressive stress exceeds target limit.")
        if max_tensile > tensile_limit:
            messages.append("Tensile stress exceeds target limit.")
        status = "pass" if not messages else "needs_adjustment"
        return ResponseEstimate(
            max_deflection_m=max_deflection,
            deflection_limit_m=deflection_limit,
            deflection_ratio=main_span / max(max_deflection, 1.0e-9),
            max_compressive_stress_pa=max_compressive,
            max_tensile_stress_pa=max_tensile,
            reaction_balance_error=0.02,
            status=status,
            governing_messages=messages,
        )


class RigidFrameOptimizer:
    """Rule-based section and tendon adjustment loop."""

    def __init__(self) -> None:
        self.evaluator = RigidFrameResponseEvaluator()

    def optimize(self, task: RigidFrameInput, initial: RigidFrameDesign) -> list[RigidFrameDesign]:
        history: list[RigidFrameDesign] = []
        current = initial
        for iteration in range(task.targets.max_iterations + 1):
            response = self.evaluator.evaluate(task, current)
            current = RigidFrameDesign(current.iteration, current.section, current.tendon_groups, response, current.actions)
            history.append(current)
            if response.status == "pass":
                break
            if iteration >= task.targets.max_iterations:
                break
            current = self._adjust(task, current, iteration + 1)
        return history

    def _adjust(self, task: RigidFrameInput, design: RigidFrameDesign, next_iteration: int) -> RigidFrameDesign:
        response = design.response
        section = design.section
        tendons = list(design.tendon_groups)
        actions: list[str] = []

        pier_height = section.pier_height_m
        midspan_height = section.midspan_height_m
        web_thickness = section.web_thickness_m
        bottom_thickness = section.bottom_slab_thickness_m
        top_thickness = section.top_slab_thickness_m

        if response and response.max_deflection_m > response.deflection_limit_m:
            pier_height *= 1.06
            midspan_height *= 1.08
            bottom_thickness *= 1.06
            tendons = [self._increase_group(group, "midspan_positive_moment", 2) for group in tendons]
            actions.append("Increased midspan depth, pier depth, bottom slab thickness, and bottom tendon count for deflection control.")

        tensile_limit = task.targets.max_tensile_stress_pa
        compressive_limit = task.targets.max_compressive_stress_pa

        if response and response.max_tensile_stress_pa > tensile_limit:
            pier_height *= 1.05
            midspan_height *= 1.04
            bottom_thickness *= 1.04
            tendons = [self._increase_group(group, "pier_top_negative_moment", 2) for group in tendons]
            tendons = [self._increase_group(group, "midspan_positive_moment", 2) for group in tendons]
            actions.append("Added top and bottom tendon capacity for tensile stress control.")

        if response and response.max_compressive_stress_pa > compressive_limit:
            pier_height *= 1.06
            midspan_height *= 1.04
            web_thickness *= 1.04
            top_thickness *= 1.08
            if response.max_tensile_stress_pa < tensile_limit * 0.25:
                tendons = [self._reduce_jacking(group, 0.99) for group in tendons]
                actions.append("Increased concrete area and slightly reduced jacking stress for compressive stress control.")
            else:
                actions.append("Increased concrete area and girder depth for compressive stress control while retaining prestress.")

        if not actions:
            midspan_height *= 1.02
            actions.append("Applied conservative section increase because response did not pass but no specific rule fired.")

        return RigidFrameDesign(
            iteration=next_iteration,
            section=SectionControl(
                pier_height_m=pier_height,
                midspan_height_m=midspan_height,
                deck_width_m=section.deck_width_m,
                web_thickness_m=web_thickness,
                bottom_slab_thickness_m=bottom_thickness,
                top_slab_thickness_m=top_thickness,
            ),
            tendon_groups=tendons,
            actions=actions,
        )

    def _increase_group(self, group: TendonGroup, role: str, increment: int) -> TendonGroup:
        if group.role != role:
            return group
        return TendonGroup(group.name, group.role, group.count + increment, group.area_each_m2, group.jacking_stress_pa, group.start_x_m, group.end_x_m, group.eccentricity_m)

    def _reduce_jacking(self, group: TendonGroup, factor: float) -> TendonGroup:
        return TendonGroup(group.name, group.role, group.count, group.area_each_m2, group.jacking_stress_pa * factor, group.start_x_m, group.end_x_m, group.eccentricity_m)


def height_at_station(task: RigidFrameInput, section: SectionControl, x_m: float) -> float:
    """Parabolic variable-depth rule for continuous rigid-frame girders."""

    pier1, pier2 = task.pier_stations_m
    half_main = task.main_span_m / 2.0
    if pier1 <= x_m <= pier2:
        distance = min(abs(x_m - pier1), abs(x_m - pier2))
        ratio = max(0.0, 1.0 - min(distance / half_main, 1.0))
    else:
        nearest = min(abs(x_m - pier1), abs(x_m - pier2))
        side_ref = max(task.side_span_left_m, task.side_span_right_m) * 0.85
        ratio = max(0.0, 1.0 - min(nearest / max(side_ref, 1.0), 1.0))
    return section.midspan_height_m + (section.pier_height_m - section.midspan_height_m) * ratio**2


def equivalent_box_properties(section: SectionControl, height_m: float) -> tuple[float, float]:
    """Return approximate area and strong-axis inertia for a single-cell box girder."""

    width = section.deck_width_m
    bottom_width = max(width * 0.42, 2.5)
    web_height = max(height_m - section.top_slab_thickness_m - section.bottom_slab_thickness_m, height_m * 0.55)
    top_area = width * section.top_slab_thickness_m
    bottom_area = bottom_width * section.bottom_slab_thickness_m
    web_area = 2.0 * section.web_thickness_m * web_height
    area = top_area + bottom_area + web_area

    top_y = height_m / 2.0 - section.top_slab_thickness_m / 2.0
    bottom_y = -height_m / 2.0 + section.bottom_slab_thickness_m / 2.0
    web_y = 0.0
    centroid = (top_area * top_y + bottom_area * bottom_y + web_area * web_y) / max(area, 1.0e-9)

    top_i = width * section.top_slab_thickness_m**3 / 12.0 + top_area * (top_y - centroid) ** 2
    bottom_i = bottom_width * section.bottom_slab_thickness_m**3 / 12.0 + bottom_area * (bottom_y - centroid) ** 2
    web_i = 2.0 * (section.web_thickness_m * web_height**3 / 12.0 + section.web_thickness_m * web_height * (web_y - centroid) ** 2)
    return area, top_i + bottom_i + web_i
