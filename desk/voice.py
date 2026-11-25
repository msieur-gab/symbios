"""voice: a recording the inbox sends to ~/Memos → a memo, its text written in the background.

The inbox's rulebook (inbox.py, ~/Inbox/rules.md) says which recordings become memos: by default those
from the companion's recorder. Each gets a folder of its own in ~/Memos, named by the recording's time (the file's own),
with a transcript written at once as transcribing. Once the text is there, the folder takes a title
from it too: the first sentence, without "so", "um", "alright"…, cut to eight words, not ending on "and", "the"…
The phrases the model mishears are put right from Gab's list, ~/Memos/words.md, and each sentence changed
is kept as heard and as meant in ~/Memos/corrections.jsonl, to train a small corrector if one is needed.

    ~/Inbox/Oct 17 at 15-58.m4a  →  ~/Memos/2026-10-17 15-58/audio.m4a       kept, for a better model later
                                    ~/Memos/2026-10-17 15-58/transcript.md   front matter (status: transcribing)
                                 →  ~/Memos/2026-10-17 15-58 That's the beginning of a new memo/
                                    transcript.md (status: done, or failed: why, the audio kept)

One memo is transcribed at a time: ffmpeg makes 16 kHz mono WAV in /tmp (memory on the board), cut at quiet moments
into chunks of about a minute (speech_chunk_seconds in desk.conf), each read by a fresh run of sherpa-onnx with
Parakeet TDT 110M (one run's memory only grows: 24 Nov, see transcribe()); Silero cuts each chunk at pauses of a second
or more (pieces of up to speech_piece_seconds; longer ones need more memory), and the pieces make paragraphs: a piece
that doesn't end a sentence goes on into the next (Gab, 2026-10-23). Activity's bar is how far the model has read. The run is capped so the board stays usable (jobs.py: on the Orange
Pi 2 of the 4 cores, lowest priority, slowed above 600 MB and stopped at 800 MB, no swap; about 28 s for a
minute of speech, peak 335–532 MB, measured 2026-10-23). A memo left transcribing by a restart is
done again: its audio is in its folder. Whisper tiny.en ran here until 2026-10-23: about twice as
slow, and it lost words that carry the meaning (brain: knowledge/speech-to-text/parakeet-tdt-110m-on-orange-pi-zero-2w.md).
After the memos, each round embeds what is new or changed (embed.py: memos once transcribed, articles however they
came), one job per document, shown in Activity as "Embedding: <title>"; a memo arriving waits behind one at most.
Heavy work runs one job at a time on the whole board, whoever starts it: each job takes a lock
(`desk-heavy.lock`, held by the job itself, so a job left running by a server that stopped keeps it
until it ends), and a server starting up stops the jobs its previous run left behind.
sherpa-onnx and the model live in a folder of their own (--stt), ~/.models/transcribe: the board's models are kept
together in ~/.models, a folder each, named after what the model does (Gab, 2026-10-23):

    bin/sherpa-onnx-vad-with-offline-asr, lib/   sherpa-onnx's linux-aarch64-shared-cpu build
    silero_vad.onnx
    parakeet-tdt-110m/{encoder,decoder,joiner}.int8.onnx, tokens.txt   sherpa's nemo-parakeet_tdt_transducer_110m-en-36000-int8

board/install.sh puts them there.

    python3 voice.py RECORDING [STT]   # transcribe one recording and print its title and paragraphs
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

import embed
import jobs

AUDIO = (".m4a", ".webm", ".ogg", ".opus", ".mp3", ".wav", ".aac", ".flac", ".3gp", ".amr")
MODEL = "parakeet tdt 110m (sherpa-onnx)"
PARAKEET = "parakeet-tdt-110m"  # its folder in --stt
# the board's own limits (jobs.py, desk.conf); on the Orange Pi: above 600 MB a job is slowed (squeezed, kept alive),
# 800 MB is the ceiling only a runaway job meets (Gab, 2026-10-21)
LIMITS = jobs.limits("job") + ["-p", "RuntimeMaxSec=1800"]
SEGMENT = re.compile(r"^([\d.]+) -- ([\d.]+): (.*)$")
NOISE = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")  # [BLANK_AUDIO], (buzzing): a sound named, not words (Whisper did)
ENDED = re.compile(r"[.?!…]$")  # a paragraph that ends a sentence
NAMES = re.compile(r"^(I|I'm|I've|I'll|I'd)$")  # words that keep their capital inside a sentence
WORDS = "words.md"  # in ~/Memos: what the model writes for what was said, Gab's list
CORRECTIONS = "corrections.jsonl"  # in ~/Memos: each sentence the list changed, as heard and as meant
STARTER = """# Words the model mishears

What the speech model writes, and what was said. Each memo is put right with this list once it is
transcribed; a change counts from the next memo. Whole phrases only: a word alone ("knots") may be
right in another memo. Every sentence the list changes is kept, as heard and as meant, in
corrections.jsonl: material to train a small corrector later, if one is needed (Gab, 2026-10-23).

| heard              | meant           |
|--------------------|-----------------|
| voice knots        | voice notes     |
| voice knot         | voice note      |
| orange pi to walk  | Orange Pi 2W    |
| orange pie to walk | Orange Pi 2W    |
| gig repository     | git repository  |
| parroting system   | operating system|
| ChPT               | ChatGPT         |
| cloud API          | Claude API      |
| web pee            | WebP            |
"""
EVERY = 10  # seconds between two looks at the inbox
NUDGE = threading.Event()  # set when a file is dropped in: look now, not at the next round
HEAVY = threading.Lock()  # this server's heavy jobs, one at a time: the one holding it runs, the others are pending
UNEMBEDDED = {}  # a document whose embedding failed → its time then: not tried again until it changes
ANNOUNCED = set()  # the Embedding tasks told as pending, so one whose file has gone is taken back
LOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid(), "desk-heavy.lock")
JOBS = "desk-heavy-%d-" % os.getpid()  # this server's jobs; set again by start(), after the home is known


def capped(run):
    """A command run as a background job the desk can live with (see the module's docstring): one at a time
    on the board, as the lock is taken inside the job."""
    return ["systemd-run", "--user", "--wait", "--pipe", "--quiet", "--unit", JOBS + str(time.time_ns()), *LIMITS,
            "flock", LOCK, "nice", "-n", "19"] + run


RATE = 16000  # the WAV ffmpeg makes: 16 kHz, mono, 16 bits
FRAME = RATE // 10  # 0.1 s: the step at which a quiet moment is looked for


def cuts(wav, chunk, reach=10):
    """Where to cut a recording into chunks of about `chunk` seconds: at the quietest 0.3 s within `reach` seconds of
    each mark, in samples, the recording's two ends included. Only the windows searched are read, not the whole file."""
    import array
    import wave
    with wave.open(wav) as w:
        total = w.getnframes()
        out, mark = [0], chunk * RATE
        while total - out[-1] > (chunk + reach) * RATE:  # the last chunk can run up to chunk + reach seconds
            lo = max(out[-1] + RATE, mark - reach * RATE)
            w.setpos(lo)
            a = array.array("h", w.readframes(2 * reach * RATE))
            loud = [sum(map(abs, a[i:i + FRAME])) for i in range(0, len(a) - FRAME + 1, FRAME)]
            quiet = min(range(len(loud) - 2), key=lambda i: loud[i] + loud[i + 1] + loud[i + 2]) if len(loud) > 2 else 0
            out.append(lo + (quiet + 1) * FRAME + FRAME // 2)  # the middle of the quietest 0.3 s
            mark = out[-1] + chunk * RATE
        return out + [total]


def transcribe(stt, recording, heard=lambda seconds: None, progress=lambda seconds: None):
    """The paragraphs said in one recording, and its length in seconds (told to heard() as soon as known); progress()
    is told how many seconds of the recording are read, each time the model gives a piece.

    Read in chunks of about a minute (speech_chunk_seconds), cut at a quiet moment, each by a fresh run of the model:
    one run's memory climbs with the length it reads and never comes down (measured 24 Nov on the Orange Pi, a 4:09
    memo: 813 MB with pieces of 30 s, 459 MB with 20 s, the same memo twice 610 MB), so a long memo outgrew the board's
    limits and was squeezed there for good, showing "almost" (Gab: "the progress should be real, and it should be
    based on what the model is doing"). A fresh run for each chunk starts again from the model alone (~150 MB)."""
    import wave
    wav = "/tmp/desk-voice-%d.wav" % os.getpid()
    part = "/tmp/desk-voice-%d-part.wav" % os.getpid()
    pieces = []
    try:
        subprocess.run(capped(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", recording, "-ar", str(RATE), "-ac", "1",
                               "-c:a", "pcm_s16le", wav]), check=True, capture_output=True, timeout=600)
        marks = cuts(wav, jobs.SPEECH_CHUNK)
        seconds = marks[-1] // RATE
        heard(seconds)
        p = os.path.join(stt, PARAKEET, "")
        run = ["env", "LD_LIBRARY_PATH=" + os.path.join(stt, "lib"),
               # each piece's line as soon as it is read (through a pipe it was kept until the end: no progress to tell)
               "stdbuf", "-oL", "-eL",
               os.path.join(stt, "bin", "sherpa-onnx-vad-with-offline-asr"), "--num-threads=2",
               "--silero-vad-model=" + os.path.join(stt, "silero_vad.onnx"),
               # cut only at a real pause, the model does best with whole sentences; 60 s pieces ran out of memory
               "--silero-vad-min-silence-duration=1.0", "--silero-vad-max-speech-duration=%d" % jobs.SPEECH_PIECE,
               # its TDT decoder: the model's CTC one, lighter, broke words ("desesign Sstem", "haveve")
               "--encoder=%sencoder.int8.onnx" % p, "--decoder=%sdecoder.int8.onnx" % p, "--joiner=%sjoiner.int8.onnx" % p,
               "--model-type=nemo_transducer", "--tokens=%stokens.txt" % p, part]
        with wave.open(wav) as src:
            for start, end in zip(marks, marks[1:]):
                src.setpos(start)
                with wave.open(part, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(RATE)
                    # a second of silence at the end, or Silero drops the last piece of a chunk that stops mid-word
                    w.writeframes(src.readframes(end - start) + bytes(2 * RATE))
                offset, ended, last = start / RATE, False, "?"
                proc = subprocess.Popen(capped(run), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    last = line.strip() or last
                    m = SEGMENT.match(line.rstrip("\n"))
                    if m and m[3].strip() and not NOISE.match(m[3]):
                        pieces.append((offset + float(m[1]), offset + float(m[2]), m[3].strip()))
                        progress(min(offset + float(m[2]), end / RATE))
                    ended = ended or line.startswith("Elapsed seconds")  # the model's last words when it read it all
                code = proc.wait(timeout=60)
                # a chunk the model didn't finish (stopped, killed at its ceiling or its time): the memo failed, its
                # audio kept; a stopped job ends with code 0, so the model's own last line is what tells
                if not ended:
                    raise RuntimeError("the transcription stopped at %d s of %d (code %d): %s" % (offset, seconds, code, last))
                progress(end / RATE)
    finally:
        for f in (wav, part):
            try:
                os.remove(f)
            except OSError:
                pass
    # a pause to think cuts a sentence in pieces: a piece that doesn't end one goes on into the next
    # (Gab, 2026-10-23, after "Abstention is what you decide to / Apply to yourself in your / Problem framing.")
    paragraphs, last = [], None
    for start, end, text in pieces:
        if last is not None and (start - last < 1.0 or not ENDED.search(paragraphs[-1])):
            first, _, rest = text.partition(" ")
            if not NAMES.match(first.rstrip(",.?!")) and first[1:].islower():
                first = first.lower()  # "Apply" goes on as "apply"; "AI", "FinTech" stay as they are
            paragraphs[-1] += " " + " ".join(filter(None, (first, rest)))
        else:
            paragraphs.append(text[:1].upper() + text[1:])
        last = end
    # a full stop before a lowercase word ends no sentence: "an important concept. are clearly" (Gab, 2026-10-23)
    return [re.sub(r"(?<=[a-z])\. (?=[a-z])", " ", p) for p in paragraphs], seconds


def words(memos):
    """Gab's list of phrases the model mishears: (heard, meant), from memos/words.md, written once if there is none."""
    path = os.path.join(memos, WORDS)
    if not os.path.exists(path):
        os.makedirs(memos, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(STARTER)
    out = []
    for line in open(path, encoding="utf-8"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and len(cells) >= 2 and cells[0] and cells[1] and cells[0].lower() != "heard" \
                and not set(cells[0] + cells[1]) <= set("-: "):
            out.append((cells[0], cells[1]))
    return out


def correct(paragraphs, pairs):
    """The paragraphs with the listed phrases put right, and each sentence changed: (as heard, as meant, phrases)."""
    out, changed = [], []
    for paragraph in paragraphs:
        sentences = []
        for sentence in re.split(r"(?<=[.?!…])\s+", paragraph):
            meant, used = sentence, []
            for heard, said in pairs:
                meant, n = re.subn(r"(?<!\w)%s(?!\w)" % re.escape(heard), lambda m: said, meant, flags=re.I)
                if n:
                    used.append(heard)
            if used:
                changed.append((sentence, meant, used))
            sentences.append(meant)
        out.append(" ".join(sentences))
    return out, changed


def remember(memos, memo, changed):
    """The memo's corrected sentences in memos/corrections.jsonl, one line each; a memo done again replaces its own."""
    path = os.path.join(memos, CORRECTIONS)
    kept = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            try:
                mine = json.loads(line).get("memo") == memo
            except ValueError:
                mine = False  # a line edited by hand is kept as it is
            if not mine and line.strip():
                kept.append(line if line.endswith("\n") else line + "\n")
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    new = [json.dumps({"memo": memo, "date": when, "model": MODEL, "heard": heard, "meant": meant, "phrases": used},
                      ensure_ascii=False) + "\n" for heard, meant, used in changed]
    if kept or new:
        with open(path + ".new", "w", encoding="utf-8") as f:
            f.writelines(kept + new)
        os.replace(path + ".new", path)


FILLER = {"so", "um", "uh", "er", "erm", "hmm", "alright", "all", "right", "okay", "ok", "well", "and", "yeah", "now"}
# words a title doesn't end on: "…about AI and what can" is "…about AI" (Gab, 2026-10-23)
DANGLING = {"a", "an", "the", "and", "or", "but", "so", "as", "of", "to", "for", "in", "on", "at", "by", "from", "with",
            "what", "which", "that", "who", "can", "could", "is", "are", "was", "be", "i", "my", "your", "his", "her", "our"}


def title(paragraphs):
    """The memo's title: its first sentence, without the words one starts talking with, eight words at most
    (a sentence of nothing but those, "Um, ok.", gives way to the next)."""
    words = []
    for sentence in re.split(r"(?<=[.?!])\s", " ".join(paragraphs).strip()):
        words = sentence.split()
        while words and words[0].lower().strip(",.!?…") in FILLER:
            words.pop(0)
        if words:
            break
    words = words[:8]
    while len(words) > 1 and words[-1].lower().strip(",.;:!?…") in DANGLING:
        words.pop()
    text = re.sub(r"[\s,.;:!?…-]+$", "", " ".join(words))
    text = re.sub(r'[/\\:*?"<>|]', " ", text).strip()  # nothing a folder name can't hold
    return text[:1].upper() + text[1:] if text else ""


def note(when, source, audio, status, text, seconds=None, name=""):
    length = "\nduration: %d:%02d" % divmod(seconds, 60) if seconds is not None else ""
    heading = name or "Memo, " + when.strftime("%-d %B %Y, %H:%M")
    return ("---\ndate: %s%s\ntitle: %s\nlanguage: en\nmodel: %s\naudio: %s\nsource: %s\nstatus: %s\n---\n\n# %s\n\n%s\n"
            % (when.strftime("%Y-%m-%d %H:%M"), length, name, MODEL, audio, source, status, heading, text))


def whole(path):
    """A recording as the phone's recorder sends it (.webm or .ogg from the browser's MediaRecorder) has no length written
    in it: a browser then shows no duration and can't seek in it (Gab, 23 Nov: "it's undefined, none, none, none,
    infinite"). Copied once into the same container, with no re-encoding (the sound byte for byte the same), it gets its
    length and its seek marks: about a second on the Lyra for a short memo. Answers its length in seconds, or None."""
    def length(p):
        try:
            return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                        capture_output=True, text=True, timeout=30).stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    seconds = length(path)
    stem, ext = os.path.splitext(path)
    if seconds is None and ext.lower() in (".webm", ".ogg", ".oga", ".opus"):
        tmp = stem + ".whole" + ext
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-c", "copy", tmp], check=True, capture_output=True, timeout=120)
            if length(tmp):
                os.replace(tmp, path)
                seconds = length(path)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return seconds


def adopt(path, memos):
    """One recording moved to a folder of its own in memos, with its transcript (as transcribing); the
    worker writes the text. Answers the folder. The inbox's rulebook decides which recordings come here."""
    f = os.path.basename(path)
    when = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    os.makedirs(memos, exist_ok=True)
    name, n, there = when.strftime("%Y-%m-%d %H-%M"), 1, os.listdir(memos)
    while any(d == name or d.startswith(name + " ") for d in there):  # two recordings in the same minute
        n += 1
        name = when.strftime("%Y-%m-%d %H-%M") + " #%d" % n
    folder = os.path.join(memos, name)
    os.makedirs(folder)
    audio = "audio" + os.path.splitext(f)[1].lower()
    os.replace(path, os.path.join(folder, audio))
    seconds = whole(os.path.join(folder, audio))  # its length in it, and known from the start (Files, the Player)
    with open(os.path.join(folder, "transcript.md"), "w", encoding="utf-8") as out:
        out.write(note(when, f, audio, "transcribing", "*Transcribing…*", round(seconds) if seconds else None))
    import signals
    signals.task("memo:" + name, label(name), "pending", "transcribe")  # in Activity at once, not at the worker's next round
    NUDGE.set()
    return folder


def waiting(memos):
    """The memos still to write: their transcript says transcribing (just taken, or cut short by a restart)."""
    out = []
    for d in sorted(os.listdir(memos)) if os.path.isdir(memos) else []:
        path = os.path.join(memos, d, "transcript.md")
        if os.path.isfile(path):
            head = open(path, encoding="utf-8").read(800)
            if "\nmodel: %s\n" % MODEL in head and "\nstatus: transcribing\n" in head:
                out.append((d, dict(re.findall(r"^(\w+): (.*)$", head.split("\n---", 1)[0], re.M))))
    return out


def worker(stt, inbox, memos, done):
    """Look at the inbox every few seconds (its rulebook places what waits there), and write the waiting
    memos one at a time."""
    import inbox as router
    import signals
    while True:
        try:
            router.sweep(os.path.dirname(inbox))
            queue = waiting(memos)
            for name, card in queue:
                signals.task("memo:" + name, label(name), "pending", "transcribe")
            for name, card in queue:
                when = datetime.datetime.strptime(card["date"], "%Y-%m-%d %H:%M")
                folder, named, id = os.path.join(memos, name), "", "memo:" + name
                try:
                    with HEAVY:
                        signals.task(id, label(name), "running", "transcribe")
                        # the bar is how far the model has read, out of the recording's length (not a guess from the clock)
                        length = [0]
                        paragraphs, seconds = transcribe(stt, os.path.join(folder, card["audio"]),
                                                         lambda s: length.__setitem__(0, s or 1),
                                                         lambda s: signals.task(id, label(name), "running",
                                                                                done=min(1.0, s / length[0])))
                    paragraphs, changed = correct(paragraphs, words(memos))
                    remember(memos, name, changed)
                    text, status, named = "\n\n".join(paragraphs) or "*(no speech heard)*", "done", title(paragraphs)
                except Exception as e:  # noqa: BLE001 — whatever went wrong is written into the transcript
                    text, status, seconds = "*Not transcribed: %s*" % e, "failed", None
                with open(os.path.join(folder, "transcript.md"), "w", encoding="utf-8") as f:
                    f.write(note(when, card.get("source", ""), card["audio"], status, text, seconds, named))
                if named and not os.path.exists(folder + " " + named):
                    os.rename(folder, folder + " " + named)
                    name += " " + named
                signals.task(id, label(name), "failed" if status == "failed" else "done")
                signals.publish("Memos", name)
                done(name)
            index(os.path.dirname(memos), memos)
        except OSError as e:
            sys.stderr.write("voice: %s\n" % e)
        NUDGE.wait(EVERY)
        NUDGE.clear()


def index(home, memos):
    """Embed the documents that wait (embed.py), one heavy job each, after the memos: when a memo arrives (or anything
    else is dropped in), the round ends after the document being embedded, and the memo goes first."""
    import signals
    if not os.path.isfile(os.path.join(embed.MODEL, "model_quantized.onnx")):
        return  # no MiniLM here (~/.models/compare, board/install.sh): nothing is embedded
    embed.orphans(home)
    queue = []
    for src, dst in embed.waiting(home):
        try:
            if UNEMBEDDED.get(src) != os.path.getmtime(src):
                queue.append((src, "embed:" + os.path.relpath(src, home), "Embedding: " + embed.card(src)[0]))
        except (OSError, ValueError):
            continue  # gone meanwhile, or not text: the job would fail on it too
    for id in ANNOUNCED - {id for _, id, _ in queue}:
        signals.drop(id)
    ANNOUNCED.clear()
    for src, id, name in queue:
        signals.task(id, name, "pending", "embed")
        ANNOUNCED.add(id)
    for src, id, name in queue:
        if NUDGE.is_set() or waiting(memos):
            return  # the rest at the next round, still pending
        ANNOUNCED.discard(id)
        if not os.path.exists(src):
            signals.drop(id)
            continue
        try:
            with HEAVY:
                signals.task(id, name, "running", "embed", expect=embed.expect(src))
                r = subprocess.run(capped([sys.executable, os.path.abspath(embed.__file__), src]), capture_output=True,
                                   text=True, timeout=1900)
        except subprocess.TimeoutExpired:
            r = subprocess.CompletedProcess([], 124, "", "stopped after 1900 s")
        if r.returncode:
            sys.stderr.write("voice: %s wasn't embedded: %s\n" % (src, (r.stderr.strip().splitlines() or ["?"])[-1]))
            try:
                UNEMBEDDED[src] = os.path.getmtime(src)
            except OSError:
                pass
        signals.task(id, name, "failed" if r.returncode else "done")


def label(name):
    """A memo as Activity says it, the work first as every line does (Gab, 2026-10-23): "Transcribing: memo 15:02",
    or "Transcribing: <its title>" once it has one."""
    stamp, _, titled = name.partition(" ")[2].partition(" ")
    return "Transcribing: " + (titled.lstrip("#0123456789 ") or "memo " + stamp.replace("-", ":"))


def wake():
    """A file was just put in the inbox: take it now."""
    NUDGE.set()


def announce(src, home):
    """A document to embed that has just arrived (an article): its line in Activity at once, pending, not when the worker
    reaches it, after every memo waiting (minutes on the Lyra: Gab, 23 Nov, "it was taking quite some time before it
    appears on the activity app")."""
    import signals
    if not os.path.isfile(os.path.join(embed.MODEL, "model_quantized.onnx")):
        return  # nothing is embedded on this device
    try:
        id, name = "embed:" + os.path.relpath(src, home), "Embedding: " + embed.card(src)[0]
    except (OSError, ValueError):
        return
    signals.task(id, name, "pending", "embed")
    ANNOUNCED.add(id)
    NUDGE.set()


def start(stt, home, done=lambda name: None):
    """The worker, in the background of the server. Jobs a previous run with this home left running are stopped
    first: their memos are still marked transcribing, so the worker does them again."""
    global JOBS
    JOBS = "desk-heavy-%s-" % hashlib.sha1(os.path.realpath(home).encode()).hexdigest()[:8]
    subprocess.run(["systemctl", "--user", "stop", JOBS + "*"], capture_output=True, timeout=30)
    threading.Thread(target=worker, args=(stt, os.path.join(home, "Inbox"), os.path.join(home, "Memos"), done),
                     daemon=True).start()


if __name__ == "__main__":
    t0 = time.time()
    found = transcribe(sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/.models/transcribe"), sys.argv[1],
                       lambda s: sys.stderr.write("%.1f heard %d s\n" % (time.time() - t0, s)),
                       lambda s: sys.stderr.write("%.1f read %.1f s\n" % (time.time() - t0, s)))[0]
    found = correct(found, words(os.path.expanduser("~/Memos")))[0]
    print("# " + title(found) + "\n\n" + "\n\n".join(found))
