#!/usr/bin/env bash
# Speech to text on the board: builds whisper.cpp, then times each model on the clips in
# bench/clips/ and writes what it found as markdown in bench/results/. See bench/README.md.
#
#   bench/stt-bench.sh                   all of it
#   MODELS="tiny base" bench/stt-bench.sh
#   SKIP_BUILD=1 bench/stt-bench.sh      reuse the build and the models already there
#
# A clip's language is the start of its name: fr-note.m4a is French, en-command.ogg English.
# A .txt next to a clip, with the same name, holds what was really said; the error rate is
# then measured against it.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$HOME/stt-bench}               # the build and the models: outside the repo
CLIPS=${CLIPS:-$HERE/clips}
MODELS=${MODELS:-"tiny tiny-q5_1 base base-q5_1"}
THREADS=${THREADS:-$(nproc)}
RUNS=${RUNS:-2}                             # the best of these is kept; the first warms the cache
REF=${WHISPER_REF:-master}
STAMP=$(date +%Y-%m-%d-%H%M)
OUT=$HERE/results/$(hostname)-$STAMP.md

say() { printf '\n== %s\n' "$*" >&2; }
temp() { local t; t=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo ""); [ -n "$t" ] && echo $((t / 1000)) || echo "?"; }

# ---- what it needs; nothing is installed without asking ----
missing=()
for tool in git cmake g++ make ffmpeg ffprobe python3; do command -v "$tool" >/dev/null || missing+=("$tool"); done
[ -x /usr/bin/time ] || missing+=("time")
if [ ${#missing[@]} -gt 0 ]; then
  pkgs=$(printf '%s\n' "${missing[@]}" | sed 's/^g++$/build-essential/; s/^make$/build-essential/; s/^ffprobe$/ffmpeg/' | sort -u | tr '\n' ' ')
  echo "Missing: ${missing[*]}" >&2
  echo "Install with: sudo apt install $pkgs" >&2
  exit 1
fi

shopt -s nullglob
clips=()
for f in "$CLIPS"/*; do case "$f" in *.txt|*/README*) ;; *) clips+=("$f") ;; esac; done
if [ ${#clips[@]} -eq 0 ]; then
  echo "No clips in $CLIPS. Put a French note (fr-…) and an English command (en-…) there; see bench/README.md." >&2
  exit 1
fi

mkdir -p "$WORK" "$HERE/results"
mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)

# ---- build whisper.cpp, natively for this CPU ----
built="reused from an earlier run"
if [ -z "${SKIP_BUILD:-}" ] || [ ! -x "$WORK/whisper.cpp/build/bin/whisper-cli" ]; then
  say "fetching whisper.cpp ($REF)"
  rm -rf "$WORK/whisper.cpp"
  git clone --depth 1 --branch "$REF" https://github.com/ggml-org/whisper.cpp "$WORK/whisper.cpp"
  jobs=$(( mem_mb < 1500 ? 2 : THREADS ))  # each compiler takes memory; a small board runs out
  say "building with $jobs jobs (this takes a while on the board)"
  start=$(date +%s)
  cmake -S "$WORK/whisper.cpp" -B "$WORK/whisper.cpp/build" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON >/dev/null
  cmake --build "$WORK/whisper.cpp/build" -j "$jobs" --config Release --target whisper-cli
  built="built in $(( $(date +%s) - start )) s"
fi
CLI=$WORK/whisper.cpp/build/bin/whisper-cli
commit=$(git -C "$WORK/whisper.cpp" rev-parse --short HEAD)

# the onnxruntime crash ("Illegal instruction") is why this is checked before anything else
set +e; "$CLI" --help >/dev/null 2>&1; code=$?; set -e
if [ $code -eq 132 ]; then echo "whisper-cli stops with Illegal instruction on this CPU (as onnxruntime did)." >&2; exit 1; fi

# ---- the models ----
for m in $MODELS; do
  [ -f "$WORK/whisper.cpp/models/ggml-$m.bin" ] || { say "downloading $m"; (cd "$WORK/whisper.cpp" && sh ./models/download-ggml-model.sh "$m" >/dev/null); }
done

# ---- each clip as whisper wants it: 16 kHz, mono ----
declare -A wav dur lang
for f in "${clips[@]}"; do
  name=$(basename "${f%.*}")
  wav[$name]=$WORK/clips/$name.wav
  mkdir -p "$WORK/clips"
  ffmpeg -loglevel error -y -i "$f" -ar 16000 -ac 1 -c:a pcm_s16le "${wav[$name]}"
  dur[$name]=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "${wav[$name]}")
  case "$name" in fr*) lang[$name]=fr ;; en*) lang[$name]=en ;; *) lang[$name]=auto ;; esac
done

# ---- the runs ----
{
  echo "# Speech to text on $(hostname), $STAMP"
  echo
  echo "- Board: $( { tr -d '\0' </proc/device-tree/model; } 2>/dev/null || echo unknown), $(nproc) cores, ${mem_mb} MB memory, $(uname -m)"
  echo "- CPU: $(lscpu 2>/dev/null | awk -F: '/Model name/ {gsub(/^ +/, "", $2); print $2; exit}')"
  echo "- System: $(. /etc/os-release && echo "$PRETTY_NAME"), kernel $(uname -r)"
  echo "- whisper.cpp $commit, ${built}, $THREADS threads, best of $RUNS runs"
  power=""; for f in /sys/class/power_supply/*/status; do power=$(cat "$f"); break; done
  echo "- Power: ${power:-no battery reported}"
  echo
  echo "Time includes loading the model, as a request that starts whisper-cli each time would pay it."
  echo "×real time below 1 means faster than the clip lasts."
  echo
  echo "| clip | model | lang | clip s | time s | ×real time | peak MB | °C before → after | word errors |"
  echo "|---|---|---|---|---|---|---|---|---|"
} >"$OUT"

transcripts=$(mktemp)
for name in "${!wav[@]}"; do
  for m in $MODELS; do
    best=""; peak=0
    before=$(temp)
    for ((r = 1; r <= RUNS; r++)); do
      say "$name · $m · run $r"
      txt=$WORK/out/$name.$m
      mkdir -p "$WORK/out"
      set +e
      /usr/bin/time -f "%e %M" -o "$WORK/time.txt" "$CLI" -m "$WORK/whisper.cpp/models/ggml-$m.bin" \
        -f "${wav[$name]}" -l "${lang[$name]}" -t "$THREADS" -nt -np -otxt -of "$txt" >/dev/null 2>"$WORK/err.txt"
      code=$?
      set -e
      if [ $code -ne 0 ]; then best="failed ($code)"; tail -3 "$WORK/err.txt" >&2; break; fi
      read -r secs kb <"$WORK/time.txt"
      [ $((kb / 1024)) -gt $peak ] && peak=$((kb / 1024))
      if [ -z "$best" ] || python3 -c "import sys; sys.exit(0 if $secs < $best else 1)"; then best=$secs; fi
    done
    after=$(temp)
    if [[ "$best" == failed* ]]; then
      echo "| $name | $m | ${lang[$name]} | ${dur[$name]%.*} | $best | | | $before → $after | |" >>"$OUT"
      continue
    fi
    rtf=$(python3 -c "print(f'{$best / ${dur[$name]}:.2f}')")
    wer=""
    [ -f "$CLIPS/$name.txt" ] && wer=$(python3 "$HERE/wer.py" "$CLIPS/$name.txt" "$txt.txt")
    echo "| $name | $m | ${lang[$name]} | ${dur[$name]%.*} | $best | $rtf | $peak | $before → $after | $wer |" >>"$OUT"
    { echo "**$name · $m**"; echo; echo "> $(tr '\n' ' ' <"$txt.txt" | sed 's/  */ /g; s/^ //')"; echo; } >>"$transcripts"
    sleep 5  # a little time to cool between models
  done
done

{ echo; echo "## What each model heard"; echo; cat "$transcripts"; } >>"$OUT"
rm -f "$transcripts"
say "written: $OUT"
cat "$OUT"
