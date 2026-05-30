"""Deterministic V7 agents for closed-loop rigid-frame prestress design.

The agents in this module deliberately separate engineering review from Abaqus
execution.  Abaqus result dictionaries are treated as a stable tool contract,
which keeps the rule system usable from a future LLM or multi-agent runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bridge_fem_agent.rigid_frame.design import RigidFrameDesign, SectionControl, TendonGroup
from bridge_fem_agent.rigid_frame.schema import RigidFrameInput


@dataclass(frozen=True)
class DesignCodeProfile:
    """Conservative preliminary review limits, not a formal code check."""

    name: str
    description: str
    service_deflection_ratio: float
    prestress_camber_ratio: float
    prestress_s11_p95_limit_pa: float
    prestress_s11_p99_limit_pa: float
    service_s11_p95_limit_pa: float
    service_s11_p99_limit_pa: float
    prestress_tensile_fraction_limit: float
    service_tensile_fraction_limit: float
    tendon_s11_min_pa: float
    tendon_s11_max_pa: float
    local_hotspot_review_pa: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class V7DiagnosticIssue:
    code: str
    severity: str
    message: str
    value: float | None = None
    limit: float | None = None
    scope: str = "global"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class V7Diagnosis:
    status: str
    metrics: dict[str, Any]
    issues: list[V7DiagnosticIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "metrics": self.metrics,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class DesignCodeAgent:
    """Resolve an auditable, conservative preliminary review profile."""

    _PROFILES = {
        "jtg3362-conservative": DesignCodeProfile(
            name="jtg3362-conservative",
            description="Conservative preliminary screening profile inspired by JTG 3362 serviceability review.",
            service_deflection_ratio=600.0,
            prestress_camber_ratio=3500.0,
            prestress_s11_p95_limit_pa=0.50e6,
            prestress_s11_p99_limit_pa=1.50e6,
            service_s11_p95_limit_pa=1.80e6,
            service_s11_p99_limit_pa=4.00e6,
            prestress_tensile_fraction_limit=0.35,
            service_tensile_fraction_limit=0.35,
            tendon_s11_min_pa=0.70e9,
            tendon_s11_max_pa=1.40e9,
            local_hotspot_review_pa=10.0e6,
        ),
        "en1992-2-conservative": DesignCodeProfile(
            name="en1992-2-conservative",
            description="Conservative preliminary screening profile inspired by EN 1992-2 serviceability review.",
            service_deflection_ratio=700.0,
            prestress_camber_ratio=4000.0,
            prestress_s11_p95_limit_pa=0.40e6,
            prestress_s11_p99_limit_pa=1.20e6,
            service_s11_p95_limit_pa=1.50e6,
            service_s11_p99_limit_pa=3.50e6,
            prestress_tensile_fraction_limit=0.30,
            service_tensile_fraction_limit=0.30,
            tendon_s11_min_pa=0.70e9,
            tendon_s11_max_pa=1.40e9,
            local_hotspot_review_pa=10.0e6,
        ),
    }

    def resolve(self, profile_name: str) -> DesignCodeProfile:
        if profile_name not in self._PROFILES:
            raise ValueError(f"Unknown V7 design-code profile: {profile_name}")
        return self._PROFILES[profile_name]


class PrestressDiagnosisAgent:
    """Convert ODB summaries into engineering issues for the outer loop."""

    def evaluate(self, task: RigidFrameInput, profile: DesignCodeProfile, odb_results: dict[str, Any]) -> V7Diagnosis:
        steps = odb_results.get("steps", {})
        prestress = steps.get("Prestress", {})
        service = steps.get("ServiceLoad", {})
        issues: list[V7DiagnosticIssue] = []

        prestress_s11 = prestress.get("concrete_s11") or {}
        service_s11 = service.get("concrete_s11") or {}
        tendon_s11 = service.get("tendon_s11") or prestress.get("tendon_s11") or {}
        prestress_u2 = prestress.get("vertical_displacement") or {}

        camber_abs = _max_abs(prestress_u2.get("min_u2"), prestress_u2.get("max_u2"))
        service_displacement = _optional_float(service.get("max_displacement"))
        prestress_p95 = _optional_float(prestress_s11.get("p95_s11"))
        prestress_p99 = _optional_float(prestress_s11.get("p99_s11"))
        service_p95 = _optional_float(service_s11.get("p95_s11"))
        service_p99 = _optional_float(service_s11.get("p99_s11"))
        service_peak_tension = _optional_float(service_s11.get("max_s11"))
        prestress_tensile_fraction = _optional_float(prestress_s11.get("tensile_fraction"))
        service_tensile_fraction = _optional_float(service_s11.get("tensile_fraction"))
        tendon_min = _optional_float(tendon_s11.get("min_s11"))
        tendon_max = _optional_float(tendon_s11.get("max_s11"))

        limits = {
            "prestress_camber_m": task.main_span_m / profile.prestress_camber_ratio,
            "service_displacement_m": task.main_span_m / profile.service_deflection_ratio,
            "prestress_s11_p95_pa": profile.prestress_s11_p95_limit_pa,
            "prestress_s11_p99_pa": profile.prestress_s11_p99_limit_pa,
            "service_s11_p95_pa": profile.service_s11_p95_limit_pa,
            "service_s11_p99_pa": profile.service_s11_p99_limit_pa,
            "prestress_tensile_fraction": profile.prestress_tensile_fraction_limit,
            "service_tensile_fraction": profile.service_tensile_fraction_limit,
            "tendon_s11_min_pa": profile.tendon_s11_min_pa,
            "tendon_s11_max_pa": profile.tendon_s11_max_pa,
            "local_hotspot_review_pa": profile.local_hotspot_review_pa,
        }
        metrics = {
            "prestress_camber_abs_m": camber_abs,
            "service_max_displacement_m": service_displacement,
            "prestress_concrete_s11": prestress_s11,
            "service_concrete_s11": service_s11,
            "service_tendon_s11": tendon_s11,
            "limits": limits,
        }

        required = {
            "prestress camber": camber_abs,
            "service displacement": service_displacement,
            "prestress concrete S11 p95": prestress_p95,
            "prestress concrete S11 p99": prestress_p99,
            "service concrete S11 p95": service_p95,
            "service concrete S11 p99": service_p99,
            "service tendon S11 minimum": tendon_min,
            "service tendon S11 maximum": tendon_max,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            issues.append(V7DiagnosticIssue("RESULTS_INCOMPLETE", "error", f"ODB summary is missing: {', '.join(missing)}."))
            return V7Diagnosis(status="needs_adjustment", metrics=metrics, issues=issues)

        _append_limit_issue(issues, "CAMBER_EXCESS", "Prestress-only camber exceeds the preliminary limit.", camber_abs, limits["prestress_camber_m"])
        _append_limit_issue(issues, "SERVICE_DEFLECTION", "Service displacement exceeds the preliminary limit.", service_displacement, limits["service_displacement_m"])
        _append_limit_issue(issues, "PRESTRESS_BROAD_TENSION_P95", "Prestress-step concrete S11 p95 indicates broad tensile stress.", prestress_p95, profile.prestress_s11_p95_limit_pa)
        _append_limit_issue(issues, "PRESTRESS_BROAD_TENSION_P99", "Prestress-step concrete S11 p99 indicates broad tensile stress.", prestress_p99, profile.prestress_s11_p99_limit_pa)
        _append_limit_issue(issues, "SERVICE_BROAD_TENSION_P95", "Service-step concrete S11 p95 exceeds the preliminary limit.", service_p95, profile.service_s11_p95_limit_pa)
        _append_limit_issue(issues, "SERVICE_BROAD_TENSION_P99", "Service-step concrete S11 p99 exceeds the preliminary limit.", service_p99, profile.service_s11_p99_limit_pa)
        if prestress_tensile_fraction is not None:
            _append_limit_issue(issues, "PRESTRESS_TENSILE_FRACTION", "Prestress-step tensile concrete sampling fraction is too large for broad-compression screening.", prestress_tensile_fraction, profile.prestress_tensile_fraction_limit)
        if service_tensile_fraction is not None:
            _append_limit_issue(issues, "SERVICE_TENSILE_FRACTION", "Service-step tensile concrete sampling fraction is too large for broad-compression screening.", service_tensile_fraction, profile.service_tensile_fraction_limit)
        if tendon_min < profile.tendon_s11_min_pa:
            issues.append(V7DiagnosticIssue("TENDON_UNDERSTRESS", "error", "Service tendon S11 is below the expected bonded-prestress range.", tendon_min, profile.tendon_s11_min_pa))
        if tendon_max > profile.tendon_s11_max_pa:
            issues.append(V7DiagnosticIssue("TENDON_OVERSTRESS", "error", "Service tendon S11 exceeds the expected bonded-prestress range.", tendon_max, profile.tendon_s11_max_pa))
        if service_peak_tension is not None and service_peak_tension > profile.local_hotspot_review_pa:
            issues.append(V7DiagnosticIssue("LOCAL_TENSILE_HOTSPOT", "warning", "Local concrete tensile hotspot requires refined support, diaphragm, and anchorage review.", service_peak_tension, profile.local_hotspot_review_pa, "local"))

        has_errors = any(issue.severity == "error" for issue in issues)
        has_warnings = any(issue.severity == "warning" for issue in issues)
        status = "needs_adjustment" if has_errors else ("pass_with_local_review" if has_warnings else "pass")
        return V7Diagnosis(status=status, metrics=metrics, issues=issues)


class PrestressOptimizationAgent:
    """Apply deterministic section and tendon changes from ODB diagnoses."""

    def adjust(self, design: RigidFrameDesign, diagnosis: V7Diagnosis, next_iteration: int) -> RigidFrameDesign:
        codes = {issue.code for issue in diagnosis.issues if issue.severity == "error"}
        section = design.section
        tendons = list(design.tendon_groups)
        actions: list[str] = []
        pier_height = section.pier_height_m
        midspan_height = section.midspan_height_m
        web_thickness = section.web_thickness_m
        bottom_thickness = section.bottom_slab_thickness_m
        top_thickness = section.top_slab_thickness_m

        if "SERVICE_DEFLECTION" in codes:
            pier_height *= 1.04
            midspan_height *= 1.06
            bottom_thickness *= 1.04
            tendons = [_increase_group(group, {"midspan_positive_moment"}, 2) for group in tendons]
            actions.append("Increased girder depth, bottom slab thickness, and midspan tendon count after service deflection review.")

        if {"PRESTRESS_BROAD_TENSION_P95", "PRESTRESS_BROAD_TENSION_P99", "PRESTRESS_TENSILE_FRACTION", "CAMBER_EXCESS"} & codes:
            pier_height *= 1.02
            midspan_height *= 1.02
            bottom_thickness *= 1.03
            top_thickness *= 1.03
            tendons = [_scale_eccentricity(group, 0.92) for group in tendons]
            tendons = [_increase_group(group, {"balanced_top_compression", "balanced_bottom_compression"}, 2) for group in tendons]
            actions.append("Reduced tendon eccentricity, increased section area, and added balanced continuity tendons after prestress-step review.")

        if {"SERVICE_BROAD_TENSION_P95", "SERVICE_BROAD_TENSION_P99", "SERVICE_TENSILE_FRACTION"} & codes:
            pier_height *= 1.03
            midspan_height *= 1.03
            web_thickness *= 1.03
            tendons = [_increase_group(group, {"pier_top_negative_moment", "midspan_positive_moment", "balanced_top_compression", "balanced_bottom_compression"}, 2) for group in tendons]
            actions.append("Added service-stage tendon capacity and section stiffness after broad concrete tension review.")

        if "TENDON_OVERSTRESS" in codes:
            tendons = [_scale_jacking(group, 0.96) for group in tendons]
            actions.append("Reduced tendon jacking stress after tendon overstress review.")

        if "TENDON_UNDERSTRESS" in codes:
            tendons = [_scale_jacking(group, 1.03) for group in tendons]
            actions.append("Increased tendon jacking stress after tendon understress review.")

        if not actions:
            midspan_height *= 1.02
            actions.append("Applied a conservative midspan-depth increase because the ODB diagnosis requires adjustment without a dedicated rule.")

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

    def adjust_for_solver(self, design: RigidFrameDesign, category: str, next_iteration: int) -> RigidFrameDesign:
        """Apply a narrow retry rule for numerical failures."""

        section = design.section
        actions = [f"Applied conservative section and eccentricity adjustment after solver category '{category}'."]
        return RigidFrameDesign(
            iteration=next_iteration,
            section=SectionControl(
                pier_height_m=section.pier_height_m * 1.02,
                midspan_height_m=section.midspan_height_m * 1.03,
                deck_width_m=section.deck_width_m,
                web_thickness_m=section.web_thickness_m * 1.02,
                bottom_slab_thickness_m=section.bottom_slab_thickness_m * 1.02,
                top_slab_thickness_m=section.top_slab_thickness_m * 1.02,
            ),
            tendon_groups=[_scale_eccentricity(group, 0.95) for group in design.tendon_groups],
            actions=actions,
        )


class SolverRepairAgent:
    """Classify solver text so the workflow can stop or retry transparently."""

    def inspect(self, attempt_dir: Path, job_name: str) -> dict[str, Any]:
        text = ""
        files: list[str] = []
        for suffix in (".sta", ".msg", ".dat", ".log"):
            path = attempt_dir / f"{job_name}{suffix}"
            if path.exists():
                files.append(str(path))
                text += "\n" + path.read_text(encoding="utf-8", errors="replace")
        upper = text.upper()
        if "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in upper:
            return {"status": "success", "category": "none", "retriable": False, "files": files}
        patterns = (
            ("temperature_region", ("TEMPERATURE", "INACTIVE"), False),
            ("embedded_region", ("EMBEDDED", "NOT FOUND"), False),
            ("zero_pivot", ("ZERO PIVOT",), True),
            ("convergence", ("TOO MANY ATTEMPTS",), True),
        )
        for category, tokens, retriable in patterns:
            if all(token in upper for token in tokens):
                return {"status": "failed", "category": category, "retriable": retriable, "files": files}
        return {"status": "failed", "category": "unclassified", "retriable": False, "files": files}


class ReviewGateAgent:
    """Make the final deterministic gate decision."""

    def review(self, diagnosis: V7Diagnosis) -> str:
        return diagnosis.status


def _append_limit_issue(issues: list[V7DiagnosticIssue], code: str, message: str, value: float, limit: float) -> None:
    if value > limit:
        issues.append(V7DiagnosticIssue(code, "error", message, value, limit))


def _max_abs(*values: Any) -> float | None:
    numeric = [abs(float(value)) for value in values if value is not None]
    return max(numeric) if numeric else None


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _increase_group(group: TendonGroup, roles: set[str], increment: int) -> TendonGroup:
    if group.role not in roles:
        return group
    return TendonGroup(group.name, group.role, group.count + increment, group.area_each_m2, group.jacking_stress_pa, group.start_x_m, group.end_x_m, group.eccentricity_m)


def _scale_eccentricity(group: TendonGroup, factor: float) -> TendonGroup:
    return TendonGroup(group.name, group.role, group.count, group.area_each_m2, group.jacking_stress_pa, group.start_x_m, group.end_x_m, group.eccentricity_m * factor)


def _scale_jacking(group: TendonGroup, factor: float) -> TendonGroup:
    return TendonGroup(group.name, group.role, group.count, group.area_each_m2, group.jacking_stress_pa * factor, group.start_x_m, group.end_x_m, group.eccentricity_m)
