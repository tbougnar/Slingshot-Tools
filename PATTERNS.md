# Pattern library

Read by the builder before every app, and by the debugger team before every
repair. This is the teaching material: everything here exists because a real
build got it wrong.

---

## A button that works

The single most common fault in a generated app is a button that renders but
does nothing. That happens when markup is written without a matching handler.

**Never leave a control without a handler.** Every single one of these needs a
listener:

```html
<button id="add">Add</button>
<script>
document.getElementById('add').addEventListener('click', addOne);
function addOne(){ /* ... */ }
</script>
```

Check your own work before finishing:

- Every `<button>` has either an `onclick` or an `addEventListener` for it
- Every `<select>` has a `change` listener
- Every `<form>` has a `submit` listener with `event.preventDefault()`
- Nothing is styled to look clickable but left inert

An element that is *meant* to be inert should not look like a button.

## Wiring existing behaviour, not inventing it

Before writing a handler, look at what the file already has. Reuse its
functions, ids and variables. A handler that calls a function name you invented
but never defined is the second most common fault.

```js
// wrong: no such function exists
btn.onclick = () => saveInvoice();

// right: the file already defines this
btn.onclick = () => saveInvoice();   // only if saveInvoice is defined below
```

If no suitable function exists, write the few lines that update the DOM or
`localStorage` directly. Keep it self-contained.

## Keeping state

```js
const KEY = 'myapp.v1';
const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || null; }
                     catch { return null; } };
const save = (v) => localStorage.setItem(KEY, JSON.stringify(v));
```

Wrap `JSON.parse` in `try`/`catch`. Saved data can be corrupt and a thrown
error on load breaks the whole app.

## Two editions from one file

```js
const PAID = new URLSearchParams(location.search).has('paid');
const LIMITS = PAID ? { max: Infinity, export: true }
                    : { max: 3, export: false };
```

Read every limit from `LIMITS`. Never hardcode a number in a comparison.

## Theme

```html
<html data-theme="dark">
<style>:root{--bg:#14100F;--acc:#C1272D;--fg:#F6EFEC}
[data-theme=light]{--bg:#FAF7F6;--fg:#1A1412}</style>
```

Toggle by setting `document.documentElement.dataset.theme` and save the choice
in `localStorage`. Read the saved value before first paint.

## Things that break silently

| Fault | What it looks like |
|---|---|
| `innerHTML` with a template literal containing `${}` from user text | blank screen |
| Listener added before the element exists | button does nothing |
| Same `id` twice | only the first is wired |
| Arrow function closing over `var` in a loop | wrong values |
| `<input type=number>` returning `""` | `NaN` everywhere |

## Size

Aim for **under 8 KB**. It is a hard constraint, not advice: the builder and the
debugger share one model allowance per minute, and a long file leaves no room
for anything to be checked or fixed. A tight app that does one job well beats a
long one that does three jobs badly.

Spend bytes on the feature and on looking good. Do not spend them on comments,
repeating markup, or defensive code for inputs you control yourself.
