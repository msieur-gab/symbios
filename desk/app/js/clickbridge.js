// Under the cog (WPE WebKit) kiosk a mouse press and release don't always become a "click",
// so buttons stay dead. After a press and release on the same spot, send the click ourselves
// unless the browser already did: a normal browser never gets two. (Learned on symbios.)
let downX = 0, downY = 0, native = false;
addEventListener("mousedown", e => { downX = e.clientX; downY = e.clientY; }, true);
addEventListener("click", e => { if (!e.bridged) native = true; }, true);
addEventListener("mouseup", e => {
  native = false;
  if (Math.abs(e.clientX - downX) > 5 || Math.abs(e.clientY - downY) > 5) return; // a drag
  const target = e.target, x = e.clientX, y = e.clientY;
  setTimeout(() => {
    if (native || !target) return;
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0 });
    click.bridged = true;
    target.dispatchEvent(click);
  }, 0);
}, true);
