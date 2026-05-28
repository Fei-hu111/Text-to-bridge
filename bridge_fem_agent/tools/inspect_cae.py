"""Inspect an Abaqus CAE file and dump high-level model metadata.

Run with Abaqus/CAE:
    abaqus cae noGUI=bridge_fem_agent/tools/inspect_cae.py -- <cae_path> <output_json>
"""

from __future__ import print_function

import json
import os
import sys

from abaqus import openMdb


def keys(repo):
    try:
        return list(repo.keys())
    except Exception:
        return []


def model_repo_keys(model, name):
    if not hasattr(model, name):
        return []
    return keys(getattr(model, name))


def inspect(cae_path):
    mdb_obj = openMdb(pathName=cae_path)
    output = {"models": {}}
    for model_name in keys(mdb_obj.models):
        model = mdb_obj.models[model_name]
        output["models"][model_name] = {
            "parts": {},
            "materials": model_repo_keys(model, "materials"),
            "sections": model_repo_keys(model, "sections"),
            "steps": model_repo_keys(model, "steps"),
            "loads": model_repo_keys(model, "loads"),
            "boundary_conditions": model_repo_keys(model, "boundaryConditions"),
            "interactions": model_repo_keys(model, "interactions"),
            "interaction_properties": model_repo_keys(model, "interactionProperties"),
            "predefined_fields": model_repo_keys(model, "predefinedFields"),
            "constraints": model_repo_keys(model, "constraints"),
            "root_assembly_sets": keys(model.rootAssembly.sets),
            "root_assembly_surfaces": keys(model.rootAssembly.surfaces),
            "instances": keys(model.rootAssembly.instances),
        }
        for part_name in keys(model.parts):
            part = model.parts[part_name]
            output["models"][model_name]["parts"][part_name] = {
                "cells": len(part.cells),
                "faces": len(part.faces),
                "edges": len(part.edges),
                "vertices": len(part.vertices),
                "sets": keys(part.sets),
                "surfaces": keys(part.surfaces),
                "section_assignments": len(part.sectionAssignments),
            }
    return output


def main(argv):
    args = [item for item in argv[1:] if item != "--"]
    if len(args) != 2:
        cae_path = os.environ.get("BRIDGE_FEM_INSPECT_CAE")
        output_json = os.environ.get("BRIDGE_FEM_INSPECT_OUT")
        if cae_path and output_json:
            args = [cae_path, output_json]
    if len(args) != 2:
        print("Usage: abaqus cae noGUI=inspect_cae.py -- <cae_path> <output_json>")
        return 2
    data = inspect(args[0])
    with open(args[1], "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
