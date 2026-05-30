"""Abaqus Python script for extracting basic bridge results from an ODB.

This file is executed by ``abaqus python`` rather than normal CPython.
"""

from __future__ import print_function

import json
import math
import sys

from odbAccess import openOdb


def vector_magnitude(data):
    return math.sqrt(sum(float(component) ** 2 for component in data))


def max_field_magnitude(frame, field_name):
    if field_name not in frame.fieldOutputs:
        return None
    values = frame.fieldOutputs[field_name].values
    if not values:
        return None
    maxima = []
    for value in values:
        if hasattr(value, "mises") and value.mises is not None:
            maxima.append(abs(float(value.mises)))
        else:
            data = value.data
            if isinstance(data, float):
                maxima.append(abs(float(data)))
            else:
                maxima.append(vector_magnitude(data))
    return max(maxima) if maxima else None


def reaction_sum(frame, assembly, set_name):
    if "RF" not in frame.fieldOutputs:
        return None
    if set_name not in assembly.nodeSets.keys():
        return None
    node_set = assembly.nodeSets[set_name]
    subset = frame.fieldOutputs["RF"].getSubset(region=node_set)
    total = [0.0, 0.0, 0.0]
    for value in subset.values:
        data = value.data
        for index in range(min(3, len(data))):
            total[index] += float(data[index])
    return {"components": total, "magnitude": vector_magnitude(total)}


def vertical_displacement_range(frame):
    if "U" not in frame.fieldOutputs:
        return None
    values = frame.fieldOutputs["U"].values
    vertical = [float(value.data[1]) for value in values if len(value.data) > 1]
    if not vertical:
        return None
    return {"min_u2": min(vertical), "max_u2": max(vertical)}


def tendon_s11_range(frame):
    if "S" not in frame.fieldOutputs:
        return None
    tendon_s11 = []
    for value in frame.fieldOutputs["S"].values:
        instance = getattr(value, "instance", None)
        instance_name = getattr(instance, "name", "").upper()
        if "TENDON" not in instance_name:
            continue
        data = value.data
        if isinstance(data, float):
            tendon_s11.append(float(data))
        elif len(data):
            tendon_s11.append(float(data[0]))
    if not tendon_s11:
        return None
    return {"min_s11": min(tendon_s11), "max_s11": max(tendon_s11)}


def concrete_principal_stress_range(frame):
    if "S" not in frame.fieldOutputs:
        return None
    max_principal = []
    min_principal = []
    for value in frame.fieldOutputs["S"].values:
        instance = getattr(value, "instance", None)
        instance_name = getattr(instance, "name", "").upper()
        if "TENDON" in instance_name:
            continue
        if hasattr(value, "maxPrincipal") and value.maxPrincipal is not None:
            max_principal.append(float(value.maxPrincipal))
        if hasattr(value, "minPrincipal") and value.minPrincipal is not None:
            min_principal.append(float(value.minPrincipal))
    if not max_principal and not min_principal:
        return None
    return {
        "max_tensile_principal": max(max_principal) if max_principal else None,
        "max_compressive_principal": min(min_principal) if min_principal else None,
    }


def concrete_s11_range(frame):
    if "S" not in frame.fieldOutputs:
        return None
    s11_values = []
    min_value = None
    max_value = None
    min_location = None
    max_location = None
    for value in frame.fieldOutputs["S"].values:
        instance = getattr(value, "instance", None)
        instance_name = getattr(instance, "name", "").upper()
        if "TENDON" in instance_name:
            continue
        data = value.data
        if isinstance(data, float):
            s11 = float(data)
        elif len(data):
            s11 = float(data[0])
        else:
            continue
        s11_values.append(s11)
        location = None
        instance = getattr(value, "instance", None)
        node_label = getattr(value, "nodeLabel", None)
        if instance is not None and node_label:
            try:
                location = list(instance.nodes[node_label - 1].coordinates)
            except Exception:
                location = None
        if min_value is None or s11 < min_value:
            min_value = s11
            min_location = location
        if max_value is None or s11 > max_value:
            max_value = s11
            max_location = location
    if not s11_values:
        return None
    ordered = sorted(s11_values)
    p95_index = int(0.95 * (len(ordered) - 1))
    p99_index = int(0.99 * (len(ordered) - 1))
    return {
        "min_s11": min_value,
        "max_s11": max_value,
        "p95_s11": ordered[p95_index],
        "p99_s11": ordered[p99_index],
        "min_location": min_location,
        "max_location": max_location,
    }


def step_summary(step):
    if not step.frames:
        return {}
    frame = step.frames[-1]
    return {
        "max_displacement": max_field_magnitude(frame, "U"),
        "max_stress": max_field_magnitude(frame, "S"),
        "vertical_displacement": vertical_displacement_range(frame),
        "tendon_s11": tendon_s11_range(frame),
        "concrete_s11": concrete_s11_range(frame),
        "concrete_principal_stress": concrete_principal_stress_range(frame),
    }


def extract(odb_path):
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        step_names = list(odb.steps.keys())
        if not step_names:
            return {}
        step = odb.steps[step_names[-1]]
        frames = step.frames
        if not frames:
            return {}
        frame = frames[-1]

        frequencies = []
        for item in frames:
            frequency = getattr(item, "frequency", None)
            if frequency is not None:
                frequencies.append(float(frequency))

        assembly = odb.rootAssembly
        support_reactions = {}
        support_sets = (
            ("left", "LEFT_SUPPORT"),
            ("right", "RIGHT_SUPPORT"),
            ("abutment_left", "ABUTMENT_LEFT"),
            ("abutment_right", "ABUTMENT_RIGHT"),
            ("pier01_base", "PIER01_BASE"),
            ("pier02_base", "PIER02_BASE"),
        )
        for output_name, set_name in support_sets:
            reaction = reaction_sum(frame, assembly, set_name)
            if reaction is not None:
                support_reactions[output_name] = reaction

        return {
            "max_displacement": max_field_magnitude(frame, "U"),
            "max_stress": max_field_magnitude(frame, "S"),
            "support_reactions": support_reactions,
            "modal_frequencies": frequencies,
            "steps": dict((name, step_summary(odb.steps[name])) for name in step_names),
        }
    finally:
        odb.close()


def main(argv):
    if len(argv) != 3:
        print("Usage: abaqus python abaqus_odb_extract.py <odb_path> <output_json>")
        return 2
    result = extract(argv[1])
    with open(argv[2], "w") as handle:
        json.dump(result, handle, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
