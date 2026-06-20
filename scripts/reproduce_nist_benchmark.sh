#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/benchmarks/nist_photon_attenuation.json"
OUTPUT_DIR="$ROOT/benchmarks/reports/nist_reproduction"
PROJECT_DIR="$ROOT/benchmarks/geant4_photon_attenuation"
BUILD_DIR="${TMPDIR:-/tmp}/radagent_geant4_photon_attenuation_build"
PYTHON_BIN=""
EVENTS=100000
REPEATS=1
SEED=12345
CASE_LIMIT=0
REFERENCE_ONLY=0
GEANT4_REQUIRED=0
SKIP_BUILD=0

usage() {
  cat <<'EOF'
RadAgent NIST benchmark reproduction

Usage:
  ./scripts/reproduce_nist_benchmark.sh [options]

Options:
  --reference-only       Generate NIST reference reports only; do not build/run Geant4
  --manifest PATH        Benchmark manifest JSON path
  --output-dir PATH      Directory for generated reports
  --events N             Histories per case for Geant4 runs (default: 100000)
  --repeats N            Repeated Geant4 runs per case (default: 1)
  --seed N               Base random seed (default: 12345)
  --case-limit N         Limit the number of manifest cases, useful for smoke runs
  --build-dir PATH       Geant4 CMake build directory
  --python COMMAND       Python interpreter; defaults to .venv/bin/python or python3
  --skip-build           Reuse the existing Geant4 benchmark executable when present
  --geant4-required      Fail if Geant4 is unavailable instead of producing reference-only output
  --help, -h             Show this help

Examples:
  ./scripts/reproduce_nist_benchmark.sh --reference-only
  ./scripts/reproduce_nist_benchmark.sh --events 100000 --repeats 1
  ./scripts/reproduce_nist_benchmark.sh --events 1000000 --repeats 3 --geant4-required
EOF
}

info() { printf '  [info] %s\n' "$*"; }
ok() { printf '  [ok] %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
fail() { printf '  [error] %s\n' "$*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reference-only)
      REFERENCE_ONLY=1
      shift
      ;;
    --manifest)
      MANIFEST="${2:?--manifest requires a path}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?--output-dir requires a path}"
      shift 2
      ;;
    --events)
      EVENTS="${2:?--events requires a value}"
      shift 2
      ;;
    --repeats)
      REPEATS="${2:?--repeats requires a value}"
      shift 2
      ;;
    --seed)
      SEED="${2:?--seed requires a value}"
      shift 2
      ;;
    --case-limit)
      CASE_LIMIT="${2:?--case-limit requires a value}"
      shift 2
      ;;
    --build-dir)
      BUILD_DIR="${2:?--build-dir requires a path}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:?--python requires a command}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --geant4-required)
      GEANT4_REQUIRED=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "$1 was not found on PATH."
    exit 1
  fi
}

geant4_available() {
  if ! command -v cmake >/dev/null 2>&1; then
    return 1
  fi
  local detect_dir
  detect_dir="$(mktemp -d "${TMPDIR:-/tmp}/radagent-geant4-detect.XXXXXX")"
  if cmake -S "$PROJECT_DIR" -B "$detect_dir" >/dev/null 2>&1; then
    rm -rf "$detect_dir"
    return 0
  fi
  rm -rf "$detect_dir"
  return 1
}

write_reference_reports() {
  local reference_json="$OUTPUT_DIR/nist_photon_attenuation_reference_report.json"
  local reference_md="$OUTPUT_DIR/nist_photon_attenuation_reference_report.md"

  info "Writing NIST reference report JSON: $reference_json"
  "$PYTHON_BIN" "$ROOT/scripts/physics_benchmark.py" \
    --manifest "$MANIFEST" \
    --output "$reference_json"

  info "Writing NIST reference report Markdown: $reference_md"
  "$PYTHON_BIN" "$ROOT/scripts/physics_benchmark.py" \
    --manifest "$MANIFEST" \
    --format markdown \
    --output "$reference_md"
}

run_geant4_reports() {
  local label="${EVENTS}"
  if [[ "$REPEATS" != "1" ]]; then
    label="${label}x${REPEATS}"
  fi
  if [[ "$CASE_LIMIT" != "0" ]]; then
    label="${label}_first${CASE_LIMIT}"
  fi

  local observations="$OUTPUT_DIR/nist_photon_attenuation_geant4_${label}_observations.json"
  local report_json="$OUTPUT_DIR/nist_photon_attenuation_geant4_${label}_report.json"
  local report_md="$OUTPUT_DIR/nist_photon_attenuation_geant4_${label}_report.md"
  local runner_args=(
    --manifest "$MANIFEST"
    --project-dir "$PROJECT_DIR"
    --build-dir "$BUILD_DIR"
    --output "$observations"
    --events "$EVENTS"
    --repeats "$REPEATS"
    --seed "$SEED"
    --case-limit "$CASE_LIMIT"
  )
  if [[ "$SKIP_BUILD" -eq 1 ]]; then
    runner_args+=(--skip-build)
  fi

  info "Running Geant4 photon attenuation benchmark."
  "$PYTHON_BIN" "$ROOT/scripts/run_photon_attenuation_geant4.py" "${runner_args[@]}"

  info "Writing evaluated NIST report JSON: $report_json"
  "$PYTHON_BIN" "$ROOT/scripts/physics_benchmark.py" \
    --manifest "$MANIFEST" \
    --observations "$observations" \
    --output "$report_json"

  info "Writing evaluated NIST report Markdown: $report_md"
  "$PYTHON_BIN" "$ROOT/scripts/physics_benchmark.py" \
    --manifest "$MANIFEST" \
    --observations "$observations" \
    --format markdown \
    --output "$report_md"
}

main() {
  cd "$ROOT"
  require_command "$PYTHON_BIN"
  mkdir -p "$OUTPUT_DIR"

  info "Repository: $ROOT"
  info "Manifest: $MANIFEST"
  info "Output directory: $OUTPUT_DIR"
  write_reference_reports

  if [[ "$REFERENCE_ONLY" -eq 1 ]]; then
    ok "Reference-only NIST reproduction finished."
    return 0
  fi

  if ! geant4_available; then
    if [[ "$GEANT4_REQUIRED" -eq 1 ]]; then
      fail "Geant4 was not detected by CMake."
      fail "Source geant4.sh or set GEANT4_INSTALL/Geant4_DIR/CMAKE_PREFIX_PATH, then rerun."
      exit 1
    fi
    warn "Geant4 was not detected by CMake; generated reference-only reports."
    warn "Rerun with --geant4-required after configuring Geant4 to require the full simulation."
    return 0
  fi

  run_geant4_reports
  ok "NIST Geant4 reproduction finished."
}

main "$@"
