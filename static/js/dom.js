/**
 * DOM helpers shared by the page modules. Text is only ever written with textContent, never
 * innerHTML, so API text cannot inject markup.
 */

/**
 * Look up a required element; a missing id is a markup bug, so fail loudly.
 * @template {HTMLElement} T
 * @param {string} id
 * @returns {T}
 */
export function byId(id) {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing element #${id}`);
  return /** @type {T} */ (element);
}

/**
 * Set the text of the first match inside a template clone.
 * @param {ParentNode} root
 * @param {string} selector
 * @param {string} text
 */
export function fill(root, selector, text) {
  const element = root.querySelector(selector);
  if (element) element.textContent = text;
}
