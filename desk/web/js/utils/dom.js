// Small helpers for drawing, that know nothing of the desk.

// an element: its tag, its class names, its text
export const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", textContent: text || "" });
