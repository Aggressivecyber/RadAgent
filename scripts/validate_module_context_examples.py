#!/usr/bin/env python3
"""Compile-check module context examples against the local Geant4 headers."""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_core.config.environment import load_environment
from agent_core.g4_codegen.module_agents.module_context_examples import (
    MODULE_LAYER_ORDER,
    get_module_code_example,
)

COMMON_PRELUDE = r"""
#include <memory>
#include <vector>
#include "G4Event.hh"
#include "G4HCofThisEvent.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4ParticleGun.hh"
#include "G4PhysListFactory.hh"
#include "G4PVPlacement.hh"
#include "G4RotationMatrix.hh"
#include "G4RunManager.hh"
#include "G4Step.hh"
#include "G4String.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "G4TouchableHistory.hh"
#include "G4VPhysicalVolume.hh"
#include "G4VSensitiveDetector.hh"
#include "G4VUserActionInitialization.hh"
#include "G4VUserDetectorConstruction.hh"
#include "G4VUserPhysicsList.hh"
#include "G4VUserPrimaryGeneratorAction.hh"

class MaterialRegistry;
class PlacementManager;
struct ScoringRecord { double value = 0.0; };
"""


MAIN_CMAKE_PRELUDE = COMMON_PRELUDE + r"""
class DetectorConstruction : public G4VUserDetectorConstruction {
public:
  G4VPhysicalVolume* Construct() override;
};
class ActionInitialization : public G4VUserActionInitialization {
public:
  void Build() const override;
};
class PhysicsListFactoryWrapper {
public:
  G4VUserPhysicsList* CreatePhysicsList();
};
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        print("missing C++ compiler: c++ or g++", file=sys.stderr)
        return 1

    geant4_config = _geant4_config_bin()
    if not geant4_config:
        print("missing geant4-config; set GEANT4_CONFIG_BIN", file=sys.stderr)
        return 1

    cflags = _geant4_cflags(geant4_config)
    with tempfile.TemporaryDirectory(prefix="radagent-example-compile-") as tmp:
        tmp_path = Path(tmp)
        failures: list[str] = []
        for module_name in MODULE_LAYER_ORDER:
            source = _source_for_module(module_name)
            source_path = tmp_path / f"{module_name}_example.cc"
            source_path.write_text(source)
            cmd = [
                compiler,
                "-std=c++17",
                "-fsyntax-only",
                *cflags,
                str(source_path),
            ]
            proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
            if proc.returncode != 0:
                failures.append(
                    f"{module_name}: {' '.join(shlex.quote(part) for part in cmd)}\n"
                    f"{proc.stderr.strip()}"
                )
        if failures:
            if args.keep_temp:
                print(f"temporary sources kept at {tmp_path}", file=sys.stderr)
            print("\n\n".join(failures), file=sys.stderr)
            return 1
        if args.keep_temp:
            print(f"temporary sources kept at {tmp_path}")
    print("module context examples compile against local Geant4 headers")
    return 0


def _geant4_config_bin() -> str:
    env = load_environment()
    candidates = [
        env.software.geant4_config_bin,
        shutil.which("geant4-config") or "",
        "/usr/local/geant4/bin/geant4-config",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return ""


def _geant4_cflags(geant4_config: str) -> list[str]:
    proc = subprocess.run(
        [geant4_config, "--cflags"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "geant4-config --cflags failed")
    return shlex.split(proc.stdout)


def _source_for_module(module_name: str) -> str:
    example = get_module_code_example(module_name)["example"]
    if module_name == "main_cmake":
        return f"{MAIN_CMAKE_PRELUDE}\nvoid validate_main_cmake_example() {{\n{example}\n}}\n"
    return f"{COMMON_PRELUDE}\n{example}\n"


if __name__ == "__main__":
    raise SystemExit(main())
