// The media service: one shared <audio> owns playback for the whole desk, so music keeps
// playing when the Music window is closed (as on symbios). The sound comes out of whatever
// device shows the desk; the board only serves the files (/api/fs/raw, seekable).
// Tracks are { name, path }; path is inside the home folder ("Music/Artist/Album/01 Song.m4a").
import { bus, sound, player, music } from "./device.js";

const audio = new Audio();
audio.preload = "metadata";
export const media = { tracks: [], idx: -1, cover: null };
const raw = path => "/api/fs/raw?path=" + encodeURIComponent(path);
const emit = type => bus.dispatchEvent(new CustomEvent(type));

export const fmt = s => { s = Math.floor(isFinite(s) && s > 0 ? s : 0); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
export const current = () => (media.idx >= 0 ? media.tracks[media.idx] : null);
export const isPlaying = () => !!audio.src && !audio.paused;
export const position = () => ({ c: audio.currentTime || 0, d: audio.duration || 0 });
export const coverUrl = () => (media.cover ? raw(media.cover) : null);

export function setQueue(tracks, idx, cover) { media.tracks = tracks || []; media.cover = cover || null; playAt(idx == null ? 0 : idx); }
export function playAt(i) {
  if (i < 0 || i >= media.tracks.length) return;
  media.idx = i;
  audio.src = raw(media.tracks[i].path);
  audio.play().catch(() => emit("media")); // a browser may want a tap first
  session();
  emit("media");
}
export function toggle() {
  if (!audio.src) { if (media.tracks.length) playAt(0); return; }
  audio.paused ? audio.play().catch(() => {}) : audio.pause();
}
export function next() { if (media.idx < media.tracks.length - 1) playAt(media.idx + 1); }
export function prev() { if (audio.currentTime > 3) audio.currentTime = 0; else if (media.idx > 0) playAt(media.idx - 1); }
export function seek(frac) { if (audio.duration) audio.currentTime = frac * audio.duration; }

// The level of the host's speakers, 0–100, for this page. "volume to 30%", "+10%", mute.
audio.volume = 0.5; // where ptiLU's volume skill starts counting
export function volume(set, relative) {
  if (set != null) audio.volume = Math.max(0, Math.min(100, relative ? audio.volume * 100 + set : set)) / 100;
  return Math.round(audio.volume * 100);
}
export function mute(on) { audio.muted = on; }
sound.volume = volume; sound.mute = mute; // what "turn the volume up" reaches

// full state on play, pause and track change; position once per second, not on every tick
// (on the board's own browser each repaint costs heat: learned on symbios)
let lastSec = -1;
audio.addEventListener("timeupdate", () => { const s = Math.floor(audio.currentTime); if (s !== lastSec) { lastSec = s; emit("media-pos"); } });
for (const type of ["play", "pause", "loadedmetadata"]) audio.addEventListener(type, () => emit("media"));
audio.addEventListener("ended", () => { if (media.idx < media.tracks.length - 1) next(); else emit("media"); });

// the host's own controls: media keys, the lock screen, a headset button
function session() {
  if (!("mediaSession" in navigator)) return;
  const t = current(), parts = t.path.split("/");
  navigator.mediaSession.metadata = new MediaMetadata({ title: t.name, artist: parts.at(-3) || "", album: parts.at(-2) || "",
    artwork: media.cover ? [{ src: raw(media.cover) }] : [] });
}
if ("mediaSession" in navigator) {
  for (const [action, run] of [["play", toggle], ["pause", toggle], ["nexttrack", next], ["previoustrack", prev]]) {
    try { navigator.mediaSession.setActionHandler(action, run); } catch { /* not offered by this browser */ }
  }
}

// ---- the player's side of the music skills: one mpc-style command in, what happened out ----
const label = t => t.name + (t.artist ? ", by " + t.artist : "");
const shuffled = list => { const a = [...list]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
player.run = async command => {
  const [verb, ...rest] = command.split(" ");
  const t = current();
  if (verb === "searchplay") {
    const name = rest.slice(1).join(" "); // after "any"
    const found = await music(name);
    if (!found.length) return "I found nothing called “" + name + "” in Music.";
    setQueue(found, 0, found[0].cover);
    return "Playing " + label(found[0]) + (found.length > 1 ? ", and " + (found.length - 1) + " more." : ".");
  }
  if (verb === "play") {
    if (t) { if (audio.paused) audio.play().catch(() => {}); return "Carrying on with " + label(t) + "."; }
    const all = shuffled(await music(""));
    if (!all.length) return "There is no music in the Music folder yet.";
    setQueue(all, 0, all[0].cover);
    return "Playing " + label(all[0]) + ", then " + (all.length - 1) + " more in any order.";
  }
  if (verb === "current") return t ? (isPlaying() ? "This is " : "Paused on ") + label(t) + (t.album ? ", from " + t.album : "") + "." : "Nothing is playing.";
  if (!t) return "Nothing is playing.";
  if (verb === "pause") { audio.pause(); return "Paused."; }
  if (verb === "stop") { audio.pause(); audio.currentTime = 0; return "Stopped."; }
  if (verb === "next") { if (media.idx >= media.tracks.length - 1) return "That was the last track."; next(); return "Next: " + label(current()) + "."; }
  if (verb === "prev") { prev(); return "Back to " + label(current()) + "."; }
  return "The player doesn't know “" + verb + "”.";
};
