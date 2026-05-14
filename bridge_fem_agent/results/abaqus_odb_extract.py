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
        left = reaction_sum(frame, assembly, "LEFT_SUPPORT")
        right = reaction_sum(frame, assembly, "RIGHT_SUPPORT")
        if left is not None:
            support_reactions["left"] = left
        if right is not None:
            support_reactions["right"] = right

        return {
            "max_displacement": max_field_magnitude(frame, "U"),
            "max_stress": max_field_magnitude(frame, "S"),
            "support_reactions": support_reactions,
            "modal_frequencies": frequencies,
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
