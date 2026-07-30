#!/usr/bin/env bash
# ---------------------------------------------------------------------
# Phase 1 flag matrix.
#
# Runs one prompt under all 64 combinations of the six OBS-01 flags and
# reports what each combination emitted.
#
# Two questions it answers:
#
#   1. Does any flag change the ANSWER?  It must not. stdout is hashed
#      for every run; every hash should match.
#   2. Does each flag produce output from its own component ONLY?
#      That is OBS-01's core acceptance criterion.
#
# On stdout hashes: Gemini is not perfectly deterministic even at
# temperature 0, so a differing hash is a SUSPICION, not a verdict. The
# three control runs at the start use identical flags (none), so any
# disagreement among them is model variance and sets the noise floor. If
# the controls disagree with each other, hash differences elsewhere
# prove nothing and you need to compare text, not hashes.
#
# Usage:
#   bash scripts/flag_matrix.sh
#   bash scripts/flag_matrix.sh "Some other prompt"
#
# Runtime: ~17 minutes for 64 runs plus 3 controls, on the PO prompt.
# ---------------------------------------------------------------------

set -u

PROMPT="${1:-What is the risk rating on PO 701337 and why?}"
OUTDIR="flag_matrix"
RUNNER="scripts/run_graph.py"

FLAGS=(
  show-parser
  show-planner
  show-raw-output
  show-synthesizer
  show-tokens
  show-timings
)

# Marker -> the component whose output it proves. Searched in stderr.
# `show-timings` has no marker on purpose: OBS-03 is not built, so the
# logger exists and stays silent. Empty output is the correct result.
declare -A MARKER=(
  [show-parser]="Intent:"
  [show-planner]="Plan:"
  [show-raw-output]="Outputs:"
  [show-synthesizer]="[debug] shape"
  [show-tokens]="Token usage:"
  [show-timings]=""
)

rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

echo "prompt : $PROMPT"
echo "outdir : $OUTDIR"
echo

# ---------------------------------------------------------------------
# Control runs — establish how much stdout varies with flags held fixed.
# ---------------------------------------------------------------------

echo "=== controls (no flags, 3 runs) ==="
for i in 1 2 3; do
  python "$RUNNER" --prompt "$PROMPT" \
    > "$OUTDIR/control_$i.out" 2> "$OUTDIR/control_$i.err"
  printf 'control %d  stdout md5 %s\n' "$i" \
    "$(md5sum < "$OUTDIR/control_$i.out" | cut -c1-12)"
done
echo

# ---------------------------------------------------------------------
# The matrix. Bit n of the run index selects FLAGS[n].
# ---------------------------------------------------------------------

echo "=== matrix (64 combinations) ==="
for mask in $(seq 0 63); do
  args=()
  label=""
  for n in $(seq 0 5); do
    if (( (mask >> n) & 1 )); then
      args+=("--${FLAGS[$n]}")
      label+="1"
    else
      label+="0"
    fi
  done

  id=$(printf '%02d_%s' "$mask" "$label")
  python "$RUNNER" --prompt "$PROMPT" "${args[@]}" \
    > "$OUTDIR/$id.out" 2> "$OUTDIR/$id.err"

  printf '%-14s %2d flag(s)  stdout md5 %s\n' \
    "$id" "${#args[@]}" \
    "$(md5sum < "$OUTDIR/$id.out" | cut -c1-12)"
done
echo

# ---------------------------------------------------------------------
# Report 1 — did the answer ever change?
# ---------------------------------------------------------------------

echo "=== stdout hashes (every run) ==="
md5sum "$OUTDIR"/*.out | awk '{print $1}' | sort | uniq -c | sort -rn
echo
echo "One line above means no flag ever altered the answer."
echo "More than one: compare the controls first — if they disagree,"
echo "it is model variance, not flag leakage."
echo

# ---------------------------------------------------------------------
# Report 2 — did each flag light only its own component?
# ---------------------------------------------------------------------

echo "=== component markers by combination ==="
printf '%-14s %-8s %-8s %-8s %-8s %-8s %-8s %-8s\n' \
  RUN parser planner rawout synth tokens summary VERDICT

fail=0
for f in "$OUTDIR"/[0-9]*.err; do
  id=$(basename "$f" .err)
  label="${id#*_}"

  row=""
  verdict="ok"
  for n in $(seq 0 5); do
    flag="${FLAGS[$n]}"
    marker="${MARKER[$flag]}"
    want="${label:$n:1}"

    if [[ -z "$marker" ]]; then
      row+=$(printf '%-8s' "-")
      continue
    fi

    if grep -qF "$marker" "$f"; then got=1; else got=0; fi
    if [[ "$got" == "$want" ]]; then
      row+=$(printf '%-8s' "$([[ $got == 1 ]] && echo yes || echo .)")
    else
      row+=$(printf '%-8s' "MISMATCH")
      verdict="FAIL"
      fail=1
    fi
  done

  # Summary is ungated: it must be present on every single run.
  if grep -qF "Summary:" "$f"; then
    summary="yes"
  else
    summary="MISSING"
    verdict="FAIL"
    fail=1
  fi

  printf '%-14s %s%-8s %-8s\n' "$id" "$row" "$summary" "$verdict"
done

echo
if (( fail )); then
  echo "RESULT: at least one combination did not match. See MISMATCH rows."
else
  echo "RESULT: every flag lit its own component and nothing else."
fi
echo
echo "Raw output kept in $OUTDIR/ — .out is stdout, .err is stderr."
