#!/usr/bin/env bash
# Summarize all 3 scenario runs: progress + smoke status + error signatures.
cd /home/rylan/RadAgent
for s in multi_layer gamma cylinder; do
  WS=$(grep -oP 'workspace=\K\S+' /tmp/cv_$s.log 2>/dev/null | head -1)
  [ -z "$WS" ] && { echo "$s: (no workspace yet)"; continue; }
  mc=$(find "$WS" -path "*model_calls*" -name "*.json" 2>/dev/null | wc -l)
  atts=$(ls -d "$WS"/jobs/*/05_codegen/integration/runtime_attempt_* 2>/dev/null)
  na=$(echo "$atts" | grep -c runtime_attempt)
  # smoke status per attempt (canonical gate)
  smk=""
  for a in $atts; do
    g=$(cat "$a/g4_output_package/smoke_simulation_result.json" 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('success'))" 2>/dev/null)
    smk="$smk $(basename $a | sed 's/runtime_attempt_/a//')=$g"
  done
  # done?
  done=$(cat /tmp/codegen_validate_result_$s.json 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print('sm_in_ctor=',d.get('sm_in_constructor_attempt0'),'codegens=',d.get('g4_codegen_status'))" 2>/dev/null)
  echo "$s: mc=$mc attempts=$na smoke=[$smk] $done"
done
echo "--- procs alive: $(pgrep -f 'python /tmp/codegen_validate' | wc -l) ---"