// Plain JavaScript, no build step. User text only ever goes into the page through
// el() / textContent, never innerHTML, because names are user input.

const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const DAY = 86400;
const EXAMPLES = [
  "find priya sharam",
  "who's in interview right now?",
  "stuck in screening for more than a week",
  "moved to interview since monday",
  "reached offer but didn't get hired",
  "everyone except rejected",
];

const state = { stages: [], people: [], stuckAfter: 7 * DAY, pending: null, searchId: 0 };
const $ = (selector) => document.querySelector(selector);

function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) node.append(kid);
  return node;
}

function span(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const d = Math.floor(seconds / DAY), h = Math.floor((seconds % DAY) / 3600), m = Math.floor((seconds % 3600) / 60);
  if (d) return h ? `${d}d ${h}h` : `${d}d`;
  return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
}
const when = (iso) => new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const label = (id) => state.stages.find((s) => s.id === id)?.label ?? id;
const isStuck = (p) => !p.is_final && p.in_stage_seconds > state.stuckAfter;
const age = (p) => (p.is_final ? `${span(p.in_stage_seconds)} ago` : span(p.in_stage_seconds));

async function api(path, options) {
  let res;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  } catch {
    throw new Error("Can't reach the server.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `The server returned ${res.status}.`);
  return body;
}

let toastTimer;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 3500);
}

// -- board --------------------------------------------------------------------

async function load() {
  try {
    const data = await api("/api/candidates");
    Object.assign(state, { stages: data.stages, people: data.candidates, stuckAfter: data.stuck_after_seconds });
    $("#demo").hidden = !data.demo;
  } catch (err) {
    return toast(err.message);
  }
  renderBoard();
  if ($("#q").value.trim()) runSearch();
}

function moveButtons(p) {
  return p.next.map((to) =>
    el("button", { type: "button", class: `act${to === "rejected" ? " reject" : ""}`, onclick: () => openMove(p, to) },
      to === "rejected" ? "Reject" : `Move to ${label(to)}`));
}

function renderBoard() {
  $("#board").replaceChildren(...state.stages.map((stage) => {
    // waiting longest first; for hired and rejected, the most recent decision first
    const people = state.people.filter((p) => p.stage === stage.id)
      .sort((a, b) => (a.is_final ? a.in_stage_seconds - b.in_stage_seconds : b.in_stage_seconds - a.in_stage_seconds));
    return el("section", { class: `column ${stage.id}` },
      el("header", {}, el("h2", {}, stage.label), el("span", { class: "count" }, String(people.length))),
      people.length
        ? el("ul", {}, people.map((p) => el("li", { class: `card${isStuck(p) ? " stuck" : ""}` },
            el("button", { type: "button", class: "name", onclick: () => openDetail(p.id) }, p.name),
            el("span", { class: "age", title: `Since ${when(p.stage_since)}` }, age(p)),
            p.is_final ? null : el("div", { class: "actions" }, moveButtons(p)))))
        : el("p", { class: "empty" }, "Nobody here"));
  }));
}

// -- search -------------------------------------------------------------------

async function runSearch() {
  const q = $("#q").value.trim(), id = ++state.searchId;
  if (!q) return showResults(null);
  let result;
  try {
    result = await api(`/api/search?q=${encodeURIComponent(q)}&tz=${encodeURIComponent(TZ)}`);
  } catch (err) {
    result = { interpretation: [], notices: [{ level: "error", message: err.message }], results: [], empty_reason: "The search didn't run." };
  }
  if (id === state.searchId) showResults(result);      // ignore answers to older keystrokes
}

function hit(p) {
  return el("li", { class: "hit" },
    el("button", { type: "button", class: "name", onclick: () => openDetail(p.id) }, p.name),
    el("span", { class: `badge ${p.stage}` }, label(p.stage)),
    el("span", { class: `age${isStuck(p) ? " stuck" : ""}` }, age(p)),
    p.reasons.length ? el("ul", { class: "reasons" }, p.reasons.map((r) => el("li", {}, r))) : null);
}

function showResults(r) {
  const box = $("#results");
  box.hidden = !r || r.mode === "browse";
  $("#board").hidden = !box.hidden;
  if (box.hidden) return;
  const parts = [];
  if (r.interpretation.length) {
    parts.push(el("ul", { class: "read-as" }, el("li", { class: "lead" }, "Read as"),
      r.interpretation.map((i) => el("li", { class: i.negated ? "neg" : "" }, i.text))));
  }
  if (r.notices.length) parts.push(el("ul", { class: "notices" }, r.notices.map((n) => el("li", { class: n.level }, n.message))));
  if (r.results.length) {
    parts.push(el("p", { class: "result-head" }, el("b", {}, String(r.results.length)), ` found, sorted ${r.order}`),
      el("ul", {}, r.results.map(hit)));
  } else {
    parts.push(el("p", { class: "empty-reason" }, r.empty_reason || "Nobody matches."));
  }
  box.replaceChildren(...parts);
}

let typing;
$("#q").addEventListener("input", () => { clearTimeout(typing); typing = setTimeout(runSearch, 220); });
$("#examples").replaceChildren(...EXAMPLES.map((text) =>
  el("button", { type: "button", class: "chip", onclick: () => { $("#q").value = text; runSearch(); } }, text)));

// -- one candidate ------------------------------------------------------------

async function openDetail(id) {
  try {
    renderDetail(await api(`/api/candidates/${id}`));
  } catch (err) {
    return toast(err.message);
  }
  if (!$("#detail").open) $("#detail").showModal();
}

function renderDetail(c) {
  const last = c.history.length - 1;
  $("#detail").replaceChildren(el("div", { class: "drawer" },
    el("header", {}, el("h2", {}, c.name), el("button", { type: "button", class: "ghost", "data-close": true }, "Close")),
    el("p", { class: `status${isStuck(c) ? " stuck" : ""}` },
      c.is_final
        ? [`${label(c.stage)} `, el("b", {}, age(c)), `, on ${when(c.stage_since)}`]
        : [`In ${label(c.stage)} for `, el("b", {}, span(c.in_stage_seconds)), `, since ${when(c.stage_since)}`]),
    c.is_final ? el("p", { class: "muted" }, `${label(c.stage)} is final and can't be changed.`) : el("div", { class: "actions" }, moveButtons(c)),
    el("section", {}, el("h3", {}, "History"),
      el("ol", { class: "history" }, c.history.map((e, i) => el("li", {},
        el("div", { class: "step" }, e.from ? `${label(e.from)} to ${label(e.to)}` : "Applied"),
        el("div", { class: "meta" }, [when(e.at), i < last ? `${span(e.seconds_in_stage)} in ${label(e.to)}` : c.is_final ? "" : `${span(e.seconds_in_stage)} so far`].filter(Boolean).join(", ")),
        e.note ? el("div", { class: "note" }, e.note) : null))))));
}

// -- moving and adding --------------------------------------------------------

function openMove(p, to) {
  state.pending = { p, to };
  const final = to === "hired" || to === "rejected";
  $("#move-title").textContent = to === "rejected" ? `Reject ${p.name}?` : `Move ${p.name} to ${label(to)}?`;
  $("#move-text").textContent = `${p.name} is in ${label(p.stage)} now. This goes into the permanent history and can't be edited.`
    + (final ? ` ${label(to)} is final, so it can't be undone.` : "");
  $("#move-confirm").textContent = to === "rejected" ? "Reject" : `Move to ${label(to)}`;
  $("#move-note").value = "";
  $("#move-error").hidden = true;
  $("#move").showModal();
}

$("#move-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const { p, to } = state.pending;
  try {
    const updated = await api(`/api/candidates/${p.id}/moves`, { method: "POST", body: JSON.stringify({ to, note: $("#move-note").value }) });
    $("#move").close();
    toast(to === "rejected" ? `${p.name} rejected.` : `${p.name} moved to ${label(to)}.`);
    if ($("#detail").open) renderDetail(updated);
  } catch (err) {
    $("#move-error").textContent = err.message;
    $("#move-error").hidden = false;
  }
  load();
});

$("#add-open").addEventListener("click", () => {
  $("#add-form").reset();
  $("#add-error").hidden = true;
  $("#add").showModal();
});

$("#add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const created = await api("/api/candidates", { method: "POST", body: JSON.stringify({ name: $("#add-name").value }) });
    $("#add").close();
    toast(`${created.name} added to Applied.`);
    load();
  } catch (err) {
    $("#add-error").textContent = err.message;
    $("#add-error").hidden = false;
  }
});

document.addEventListener("click", (event) => {
  const close = event.target.closest("[data-close]");
  if (close) close.closest("dialog").close();
  if (event.target.tagName === "DIALOG") event.target.close();      // a click on the backdrop
});

load();
