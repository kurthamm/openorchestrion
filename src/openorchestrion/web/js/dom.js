/** Minimal DOM helpers. Text is always set via textContent, never innerHTML. */

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') element.className = value;
    else if (key === 'dataset') Object.assign(element.dataset, value);
    else if (key === 'style') Object.assign(element.style, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      element.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'text') element.textContent = value;
    else if (value === true) element.setAttribute(key, '');
    else element.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function render(node, ...children) {
  node.replaceChildren(...children.flat().filter(Boolean));
  return node;
}

/** A labelled status line — used for every degraded state in the UI. */
export function notice(tone, title, detail) {
  return h(
    'div',
    { class: `notice notice-${tone}`, role: tone === 'bad' ? 'alert' : 'status' },
    h('strong', { text: title }),
    detail ? h('span', { text: detail }) : null,
  );
}
