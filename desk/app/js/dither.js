// dither.js — ordered (Bayer 4x4) dithering of an image to two theme colours.
// Maps any photo to --fg ink on --bg paper; the ink/paper test flips based on
// which colour is darker, so images read right on paper (dark ink) and on
// phosphor/amber (bright ink). Shared by Reader (web images) and Music (album
// covers) for the retro 1-bit look; re-run on 'themechange' to recolour.
const BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
const hexToRgb = (h) => { const n = parseInt(h.replace('#', ''), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const lumaOf = ([r, g, b]) => 0.299 * r + 0.587 * g + 0.114 * b;

// Live theme colours as [fgHex, bgHex].
export function themeColors() {
  const cs = getComputedStyle(document.documentElement);
  return [cs.getPropertyValue('--fg').trim() || '#161616',
          cs.getPropertyValue('--bg').trim() || '#ffffff'];
}

// Dither `img` into `canvas`. `maxW` caps the long edge (perf). Returns false if
// the image can't be read (tainted / zero-size).
export function paintDither(canvas, img, fgHex, bgHex, maxW = 520) {
  if (!img.naturalWidth) return false;
  const scale = img.naturalWidth > maxW ? maxW / img.naturalWidth : 1;
  const w = Math.max(1, Math.round(img.naturalWidth * scale));
  const h = Math.max(1, Math.round(img.naturalHeight * scale));
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, w, h);
  let id;
  try { id = ctx.getImageData(0, 0, w, h); } catch (e) { return false; }
  const d = id.data;
  const fg = hexToRgb(fgHex), bg = hexToRgb(bgHex);
  const darkInk = lumaOf(fg) < lumaOf(bg);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    const lum = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    const t = (BAYER4[y & 3][x & 3] + 0.5) / 16 * 255;
    const ink = darkInk ? lum < t : lum > t;
    const px = ink ? fg : bg;
    d[i] = px[0]; d[i + 1] = px[1]; d[i + 2] = px[2]; d[i + 3] = 255;
  }
  ctx.putImageData(id, 0, 0);
  return true;
}
