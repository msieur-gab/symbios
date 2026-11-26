# Speech to text on the board: benchmark

Finds out whether the board can turn speech into text by itself, and how fast. Its numbers decide
the voice notes and voice commands planned in `TODO.md` (Inbox and voice).

What it measures: whisper.cpp, built on the board for its own CPU, with four models (tiny and
base, each also in a smaller quantized form, `q5_1`). For each clip and model: the time taken,
how that compares with the clip's length, the most memory used, the board's temperature before
and after, and, when the real words are given, the share of words it got wrong.

Why whisper.cpp first: it is C++ with no Python packages and no onnxruntime, which crashes on
this board ("Illegal instruction"). It is the same family as llama.cpp, the route proposed for
MiniLM, so a good build here says that route will build too.

## Before running

1. **Record two clips on the phone**, in a quiet room, as you would really use it:
   - `fr-note`: about a minute of a French voice note, spoken naturally.
   - `en-command`: a short English command for ptiLU, such as "make a folder called drafts".
   - More are welcome (`fr-…`, `en-…`): a note outside, a note in English. The start of the name
     gives the language.
2. **Put them in `bench/clips/`** on the board, in any format the phone gives (m4a, ogg, wav).
   This folder is not committed: these are recordings of a voice.
3. **Optionally, write what was said** in a `.txt` with the same name (`fr-note.txt`). The error
   rate is measured only for clips that have one.
4. **Plug the board in** for the run: it is long, and power changes the speed.

## Running it

```
bench/stt-bench.sh
```

It stops at once and names the packages to install if any is missing (git, cmake, a compiler,
ffmpeg, `time`). The build and the models go to `~/stt-bench`, outside the repo (about 400 MB).
The build alone can take 20 minutes or more on the board.

- `MODELS="tiny base"` to try fewer models; `base-q8_0`, `small-q5_1` exist too.
- `SKIP_BUILD=1` reruns with the build and models already there, after adding a clip.
- `RUNS=1` for a quicker pass.

## What comes back

A markdown file in `bench/results/`, named after the board and the time: the board's facts, a
table per clip and model, and what each model heard. Commit it on this branch.

How to read it:

- **×real time** below 1 means faster than the clip lasts. For a note transcribed in the
  background, up to 2 or 3 is fine on power. For a command, what matters is the time in
  seconds: about 2 is the most that feels like an answer.
- **The time includes loading the model.** A command that starts whisper-cli each time pays it.
  A server that keeps the model loaded would not; if loading turns out to be most of the time,
  that is the next thing to test.
- **Peak memory** next to the board's total says whether base fits beside the desk, the kiosk
  and the rest.

## For a session on the board

Run the steps above, with these in mind:

- Ask Gab before installing packages with sudo, and before deleting anything in `~/stt-bench`.
- If the build fails or whisper-cli stops with "Illegal instruction", keep the full error and
  the output of `lscpu`, and commit them in `bench/results/` instead of the table.
- Don't change `stt-bench.sh` to make a failure pass. Fix what is wrong in it, say what changed
  in the commit, and rerun.
- Commit the results file on the `audio-notes` branch and push it. The clips stay off git.

## The search test page (2026-10-23)

`search_page.py` asks the board's articles and memos in a browser, from the vector files the desk writes
(`embed.py`). It is not part of the desk and doesn't run by default (112 MB while it runs; stopped on 2026-10-23,
Gab: "yes kill the search process"). On the board, with the scripts in `~/bench-search`, start it for a test
session with:

    systemd-run --user --unit=bench-search-page -p MemoryMax=300M -p CPUQuota=200% -p CPUWeight=idle -p Nice=19 \
      -p WorkingDirectory=/home/you/bench-search -E PYTHONPATH=/home/you/.models/shared/python \
      python3 search_page.py /home/you 8091

then open `http://<board>:8091/`. Stop it with `systemctl --user stop bench-search-page`; a reboot stops it too.
