import { date, lang, num, setLang, t, tn, translateDom } from "./i18n.js?v=16";

const main = document.getElementById("main");
const topbar = document.getElementById("topbar");
const toasts = document.getElementById("toasts");
const badge = document.getElementById("dl-badge");

const ICON = {
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11m0 0 4.5-4.5M12 15l-4.5-4.5M5 19h14"/></svg>',
  chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z"/></svg>',
  open: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3"/></svg>',
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20a2 2 0 0 0 4 0"/></svg>',
  key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M14 9l2 2"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/></svg>',
};

class AuthError extends Error {}
class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

const statusLabel = (status) => (status ? t(`status.${status}`) : "");
const spinner = '<span class="spinner" aria-hidden="true"></span>';
const loadingLine = () => `<p class="loading-line">${spinner}${esc(t("common.loading"))}</p>`;

function variantName(name) {
  const key = `variant.${name}`;
  const label = t(key);
  return label === key ? name : label;
}

function fmtSize(bytes) {
  if (!bytes) return `0 ${t("unit.MB")}`;
  const gb = bytes / 1e9;
  if (gb >= 1) return `${num(gb, { maximumFractionDigits: gb >= 10 ? 0 : 1 })} ${t("unit.GB")}`;
  return `${num(Math.max(1, Math.round(bytes / 1e6)))} ${t("unit.MB")}`;
}

function fmtSpeed(bps) {
  if (!bps) return "";
  const mb = bps / 1e6;
  return mb >= 1 ? `${num(mb, { maximumFractionDigits: 1 })} ${t("unit.MBs")}` : `${Math.round(bps / 1e3)} ${t("unit.kBs")}`;
}

function fmtEta(seconds) {
  if (!seconds) return "";
  if (seconds < 60) return t("dl.lessThanMinute");
  const min = Math.round(seconds / 60);
  if (min < 60) return t("dl.minutesLeft", { min });
  return t("dl.hoursLeft", { h: Math.floor(min / 60), min: String(min % 60).padStart(2, "0") });
}

function runs(nums) {
  const sorted = [...new Set(nums)].sort((a, b) => a - b);
  const out = [];
  for (const n of sorted) {
    const last = out[out.length - 1];
    if (last && n === last[1] + 1) last[1] = n;
    else out.push([n, n]);
  }
  return out;
}

function humanVolumes(nums, withWord = true) {
  const list = [...new Set(nums.filter((n) => n >= 0))];
  if (!list.length) return "";
  const and = t("common.and");
  const parts = runs(list).map(([a, b]) => (a === b ? `${a}` : b === a + 1 ? `${a} ${and} ${b}` : `${a} ${t("common.to")} ${b}`));
  const text = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} ${and} ${parts[parts.length - 1]}` : parts[0];
  return withWord ? `${tn(list.length, "n.Volume", false)} ${text}` : text;
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { "X-Lire-Lang": lang };
  if (method !== "GET") headers["X-Lire"] = "1";
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: "same-origin" });
  } catch {
    throw new ApiError(t("err.offline"), 0);
  }
  if (response.status === 401 && path !== "/api/login") {
    renderLogin();
    throw new AuthError();
  }
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) throw new ApiError(data?.detail || t("err.status", { status: response.status }), response.status);
  return data;
}

function toast(message, bad = false) {
  const el = document.createElement("div");
  el.className = `toast${bad ? " bad" : ""}`;
  el.textContent = message;
  toasts.append(el);
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 400);
  }, bad ? 7000 : 4500);
}

function storageGet(store, key) {
  try { return store.getItem(key) || ""; } catch { return ""; }
}

function storageSet(store, key, value) {
  try { store.setItem(key, value); } catch { /* private mode: nothing to remember */ }
}

const me = { username: "", role: "", oidc: null, kavitaLinked: true };

async function loadSession() {
  const s = await api("/api/session");
  me.username = s.user?.username || "";
  me.role = s.user?.role || "";
  me.oidc = s.oidc || null;
  me.kavitaLinked = Boolean(s.kavita_linked);
  document.getElementById("nav-accounts").hidden = me.role !== "admin";
  document.getElementById("me-name").textContent = me.username;
  return s.auth;
}

let renderToken = 0;
let pollTimer = null;
const session = { query: storageGet(sessionStorage, "lire:q") };

function setView(html, { nav = null, focus = true } = {}) {
  main.innerHTML = html;
  main.firstElementChild?.classList.add("view-enter");
  topbar.hidden = false;
  for (const a of topbar.querySelectorAll("[data-nav]")) {
    if (a.dataset.nav === nav) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  if (focus) main.focus({ preventScroll: true });
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

/** Repeat a refresh while the page stays on the same view and the tab is visible. */
function poll(token, every, fn) {
  stopPolling();
  pollTimer = setInterval(() => {
    if (token !== renderToken) return stopPolling();
    if (!document.hidden) fn().catch(() => {});
  }, every);
}

function parseRoute() {
  const hash = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = hash.split("?");
  return { parts: path.split("/").filter(Boolean), params: new URLSearchParams(qs || "") };
}

async function route() {
  stopPolling();
  const token = ++renderToken;
  const { parts, params } = parseRoute();
  window.scrollTo({ top: 0 });
  try {
    if (parts[0] === "serie" && parts[1]) return await renderSeries(token, Number(parts[1]), params);
    if (parts[0] === "bd") return await renderSeries(token, null, params);
    if (parts[0] === "telechargements") return await renderDownloads(token);
    if (parts[0] === "chercher") return await renderHome(token);
    if (parts[0] === "comptes" && me.role === "admin") return await renderAccounts(token);
    return await renderLibrary(token, { kind: params.get("type") === "bd" ? "comics" : "manga" });
  } catch (err) {
    if (err instanceof AuthError || token !== renderToken) return;
    setView(`<div class="page"><a class="back" href="#/chercher">${ICON.back} ${esc(t("common.back"))}</a>${errorBox(err.message, true)}</div>`);
    main.querySelector("[data-retry]")?.addEventListener("click", route);
  }
}

function errorBox(message, retry = false) {
  return `<div class="error-box" role="alert"><strong>${esc(t("err.title"))}</strong><p>${esc(message)}</p>${retry ? `<button class="btn" type="button" data-retry>${esc(t("err.retry"))}</button>` : ""}</div>`;
}

/* ---------- Language ---------- */

function langButton(id) {
  return `<button class="btn btn-quiet btn-small lang-switch" type="button" id="${id}" lang="${lang === "fr" ? "en" : "fr"}" aria-label="${esc(t("lang.label"))}">${esc(t("lang.switch"))}</button>`;
}

function switchLang() {
  setLang(lang === "fr" ? "en" : "fr");
  translateDom();
  syncLangButton();
  if (topbar.hidden) renderLogin();
  else route();
}

function syncLangButton() {
  const button = document.getElementById("lang");
  button.textContent = t("lang.switch");
  button.setAttribute("aria-label", t("lang.label"));
  button.lang = lang === "fr" ? "en" : "fr";
}

/* ---------- Login ---------- */

/** Error code sent back by the single sign-on callback (?login_error=...), shown once then dropped from the URL. */
function ssoError() {
  const params = new URLSearchParams(location.search);
  const code = params.get("login_error");
  if (!code) return "";
  history.replaceState(null, "", location.pathname + location.hash);
  const key = `login.error.${code}`;
  const text = t(key);
  return text === key ? t("login.error.sso_down") : text;
}

/** Same domain as Kavita: when its session is open in this browser, hand the reader's own key to Lire once. */
async function linkKavitaFromSession() {
  if (me.kavitaLinked) return;
  try {
    const r = await fetch("/kavita/api/Account/auth-keys", { credentials: "same-origin" });
    if (!r.ok) return;
    const keys = await r.json();
    const key = (keys.find((k) => k.name === "opds") || keys[0])?.key;
    if (!key) return;
    await api("/api/me/kavita-key", { method: "POST", body: { key } });
    me.kavitaLinked = true;
  } catch { /* no Kavita session yet: the library offers to open Kavita once */ }
}

function renderLogin() {
  stopPolling();
  renderToken++;
  topbar.hidden = true;
  main.innerHTML = `
    <div class="login view-enter">
      <form class="login-box" novalidate>
        <div class="login-mark" aria-hidden="true">Lire<span>.</span></div>
        <h1 class="visually-hidden">${esc(t("login.title"))}</h1>
        <p>${esc(t("app.tagline"))}</p>
        ${me.oidc ? `<a class="btn btn-primary btn-sso" href="/api/auth/oidc/start">${ICON.key} ${esc(t("login.sso", { name: me.oidc.name }))}</a>
          <p class="login-or"><span>${esc(t("login.or"))}</span></p>` : ""}
        <p class="form-error" id="sso-error" aria-live="assertive">${esc(ssoError())}</p>
        <div class="field">
          <label for="user">${esc(t("login.user"))}</label>
          <input class="input" id="user" name="username" type="text" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false" required value="${esc(storageGet(localStorage, "lire:user"))}">
        </div>
        <div class="field">
          <label for="pw">${esc(t("login.password"))}</label>
          <input class="input" id="pw" name="password" type="password" autocomplete="current-password" autocapitalize="none" autocorrect="off" spellcheck="false" required>
        </div>
        <p class="form-error" id="pw-error" aria-live="assertive"></p>
        <button class="btn ${me.oidc ? "" : "btn-primary"}" type="submit">${esc(t("login.submit"))}</button>
        <div class="login-lang">${langButton("login-lang")}</div>
      </form>
    </div>`;
  const form = main.querySelector("form");
  const userInput = form.querySelector("#user");
  const input = form.querySelector("#pw");
  const error = form.querySelector("#pw-error");
  const button = form.querySelector('button[type="submit"]');
  form.querySelector("#login-lang").addEventListener("click", switchLang);
  (userInput.value ? input : userInput).focus();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = userInput.value.trim().toLowerCase();
    if (!username || !input.value) { error.textContent = t("login.missing"); return; }
    button.disabled = true;
    button.innerHTML = `${spinner} ${esc(t("login.busy"))}`;
    try {
      await api("/api/login", { method: "POST", body: { username, password: input.value } });
      storageSet(localStorage, "lire:user", username);
      await loadSession();
      route();
      refreshBadge();
    } catch (err) {
      error.textContent = err.message;
      button.disabled = false;
      button.textContent = t("login.submit");
      input.select();
    }
  });
}

/* ---------- Home / search ---------- */

function coverHtml(src, title) {
  return src
    ? `<img src="${esc(src)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">`
    : `<span class="cover-fallback">${esc(title)}</span>`;
}

function resultCard(card, query) {
  const meta = [card.year, card.volumes ? tn(card.volumes, "n.volume") : null, statusLabel(card.status),
    card.format === "ONE_SHOT" ? t("home.oneShot") : null].filter(Boolean).join(" · ");
  return `
    <a class="cover-link" href="#/serie/${card.id}?q=${encodeURIComponent(query)}">
      <div class="cover">${coverHtml(card.cover, card.title)}</div>
      <div class="cover-title">${esc(card.title)}</div>
      <div class="cover-meta">${esc(meta)}</div>
    </a>`;
}

async function renderHome(token) {
  const isBd = storageGet(sessionStorage, "lire:mode") === "bd";
  setView(`
    <div class="page">
      <section class="search-hero" aria-labelledby="home-title">
        <h1 id="home-title">${esc(t(isBd ? "home.bdTitle" : "home.mangaTitle"))}</h1>
        <div class="editions" role="group" aria-label="${esc(t("home.kind"))}">
          <button type="button" data-mode="manga" aria-pressed="${!isBd}">${esc(t("home.mangas"))}</button>
          <button type="button" data-mode="bd" aria-pressed="${isBd}">${esc(t("home.comics"))}</button>
        </div>
        <form class="search-box" role="search">
          ${ICON.search}
          <label class="visually-hidden" for="q">${esc(t(isBd ? "home.bdLabel" : "home.mangaLabel"))}</label>
          <input class="input" id="q" type="search" placeholder="${esc(t(isBd ? "home.bdPlaceholder" : "home.mangaPlaceholder"))}" autocomplete="off" autocorrect="off" spellcheck="false" enterkeyhint="search" value="${esc(isBd ? storageGet(sessionStorage, "lire:qbd") : session.query)}">
          <span class="spinner" id="q-spin" hidden aria-hidden="true"></span>
        </form>
        <p class="hint">${esc(t(isBd ? "home.bdHint" : "home.mangaHint"))}</p>
      </section>
      <div id="results" aria-live="polite"></div>
      <div id="home-extra"></div>
    </div>`, { nav: "home", focus: false });

  main.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
    storageSet(sessionStorage, "lire:mode", b.dataset.mode);
    renderHome(++renderToken);
  }));
  const input = main.querySelector("#q");
  const spin = main.querySelector("#q-spin");
  const results = main.querySelector("#results");
  const extra = main.querySelector("#home-extra");

  if (isBd) {
    main.querySelector("form").addEventListener("submit", (event) => {
      event.preventDefault();
      const q = input.value.trim();
      if (q.length < 2) return;
      storageSet(sessionStorage, "lire:qbd", q);
      location.hash = `#/bd?${new URLSearchParams({ q })}`;
    });
    loadHomeExtra(token, extra, true);
    return;
  }

  let timer = null;
  let searchToken = 0;

  async function runSearch(q) {
    session.query = q;
    storageSet(sessionStorage, "lire:q", q);
    const mine = ++searchToken;
    if (q.trim().length < 2) {
      results.innerHTML = "";
      extra.hidden = false;
      spin.hidden = true;
      return;
    }
    spin.hidden = false;
    try {
      const data = await api(`/api/search?q=${encodeURIComponent(q.trim())}`);
      if (mine !== searchToken || token !== renderToken) return;
      extra.hidden = true;
      results.innerHTML = data.results.length
        ? `<section class="section" aria-label="${esc(t("home.results"))}"><div class="covers">${data.results.map((c) => resultCard(c, q.trim())).join("")}</div></section>`
        : `<div class="section empty"><strong>${esc(t("home.noResult", { q }))}</strong><span>${esc(t("home.noResultHint"))}</span></div>`;
    } catch (err) {
      if (err instanceof AuthError || mine !== searchToken) return;
      results.innerHTML = `<div class="section">${errorBox(err.message)}</div>`;
    } finally {
      if (mine === searchToken) spin.hidden = true;
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => runSearch(input.value), 380);
  });
  main.querySelector("form").addEventListener("submit", (event) => {
    event.preventDefault();
    clearTimeout(timer);
    input.blur();
    runSearch(input.value);
  });

  if (session.query.trim().length >= 2) runSearch(session.query);
  loadHomeExtra(token, extra);
}

const isActive = (g) => g.status !== "done";

const bdHash = (q) => `#/bd?${new URLSearchParams({ q })}`;

function pickCard(p) {
  return `
    <a class="cover-link" href="${esc(bdHash(p.query))}">
      <div class="cover">${coverHtml(p.cover, p.title)}</div>
      <div class="cover-title">${esc(p.title)}</div>
      <div class="cover-meta">${esc(p.authors)}</div>
    </a>`;
}

function newsRow(n) {
  const when = n.date ? relTime(Date.parse(n.date) / 1000) : "";
  return `
    <a class="dl-row news-row" href="${esc(bdHash(n.title))}">
      <div>
        <div class="dl-name">${esc(n.title)}</div>
        <div class="dl-status">${esc([when, tn(n.seeders, "n.source"), fmtSize(n.size)].filter(Boolean).join(" · "))}</div>
      </div>
      <div class="dl-side">${ICON.chevron}</div>
    </a>`;
}

async function loadHomeExtra(token, container, isBd = false) {
  const [downloads, found] = await Promise.allSettled([api("/api/downloads"), api(`/api/discover?kind=${isBd ? "comics" : "manga"}`)]);
  if (token !== renderToken) return;
  let html = "";
  if (downloads.status === "fulfilled") {
    const active = downloads.value.groups.filter(isActive);
    if (active.length) {
      html += `<section class="section" aria-labelledby="h-active">
        <div class="section-head"><h2 id="h-active">${esc(t("home.active"))}</h2><a href="#/telechargements">${esc(t("common.seeAll"))}</a></div>
        <div class="dl-list">${active.slice(0, 3).map(downloadRow).join("")}</div></section>`;
    }
  }
  if (found.status === "fulfilled" && isBd) {
    const { picks, news } = found.value;
    html += `<section class="section" aria-labelledby="h-picks">
      <div class="section-head"><h2 id="h-picks">${esc(t("disc.picks"))}</h2></div>
      <div class="rail">${picks.map(pickCard).join("")}</div></section>`;
    if (news.length) {
      html += `<section class="section" aria-labelledby="h-news">
        <div class="section-head"><h2 id="h-news">${esc(t("disc.news"))}</h2></div>
        <div class="dl-list">${news.slice(0, 6).map(newsRow).join("")}</div></section>`;
    }
  } else if (found.status === "fulfilled") {
    for (const [key, cards] of [["disc.trending", found.value.trending], ["disc.popular", found.value.popular]]) {
      if (!cards.length) continue;
      html += `<section class="section" aria-label="${esc(t(key))}">
        <div class="section-head"><h2>${esc(t(key))}</h2></div>
        <div class="rail">${cards.map((c) => resultCard(c, c.title)).join("")}</div></section>`;
    }
  }
  if (!html) {
    html = `<section class="section empty"><strong>${esc(t("home.empty"))}</strong><span>${esc(t("home.emptyHint"))}</span></section>`;
  }
  container.innerHTML = html;
  applyStagger(container);
}

/* ---------- Series ---------- */

function releaseRow(r, { checked = false, disabled = false } = {}) {
  const kind = r.volumes.length > 1 ? t("release.pack") : t("release.single");
  const origin = r.official ? `<span class="tag good">${esc(t("release.official"))}</span>` : r.unofficial ? `<span class="tag">${esc(t("release.unofficial"))}</span>` : "";
  const fmt = r.format ? `<span class="tag">${esc(r.format.toUpperCase())}</span>` : "";
  const state = r.state === "downloading" ? `<span class="tag state">${esc(t("release.downloading"))}</span>`
    : r.state === "done" ? `<span class="tag state">${esc(t("release.done"))}</span>` : "";
  const vols = r.volumes.length ? humanVolumes(r.volumes, false) : "?";
  return `
    <label class="release"${disabled ? ' aria-disabled="true"' : ""}>
      <input type="checkbox" name="rel" value="${esc(r.key)}" data-size="${Number(r.size) || 0}" data-vols="${r.volumes.map(Number).join(",")}"${checked ? " checked" : ""}${disabled ? " disabled" : ""}>
      <span class="check" aria-hidden="true">${ICON.check}</span>
      <span class="rel-vols">${esc(vols)}<small>${esc(kind)}</small></span>
      <span class="rel-main">
        <span class="rel-desc">${origin}${fmt}${state}<span>${esc(tn(r.seeders, "n.source"))}</span></span>
        <span class="rel-raw" title="${esc(r.title)}">${esc(r.title)}</span>
      </span>
      <span class="rel-size"><strong>${esc(fmtSize(r.size))}</strong></span>
    </label>`;
}

function shelfHtml(data) {
  const spines = data.shelf.map((s, i) =>
    `<li class="spine" data-state="${s.state}" data-i="${Math.min(i, 80)}" aria-label="${esc(t("series.spine", { n: s.n, state: t(`shelf.${s.state}`) }))}"><span aria-hidden="true">${s.n}</span></li>`).join("");
  const c = data.counts;
  const legend = [
    ["owned", c.owned], ["downloading", c.downloading], ["planned", c.planned],
    ["missing", Math.max(0, c.missing - c.dead)], ["dead", c.dead],
  ].filter(([, n]) => n > 0)
    .map(([state, n]) => `<span><i data-state="${state}"></i><b>${n}</b> ${esc(t(`shelf.${state}`))}</span>`).join("");
  return `<ol class="shelf" aria-label="${esc(t("series.shelfLabel", { n: data.shelf.length }))}">${spines}</ol><div class="legend">${legend}</div>`;
}

function verdict(data) {
  const c = data.counts;
  const picks = data.plan.picks;
  if (!data.found) return [t("verdict.nothing"), t("verdict.nothingSub")];
  if (picks.length) {
    const vols = picks.flatMap((p) => p.volumes).filter((n) => n >= 1);
    return [t("verdict.toGet", { vols: humanVolumes(vols) }),
      t("verdict.toGetSub", { torrents: tn(picks.length, "n.torrent"), size: fmtSize(data.plan.size), folder: data.folder })];
  }
  if (c.horizon && c.owned >= c.horizon) return [t("verdict.complete"), t("verdict.completeSub")];
  if (c.downloading) return [t("verdict.coming"), t("verdict.comingSub")];
  return [t("verdict.dead"), t("verdict.deadSub")];
}

function applyStagger(root) {
  root.querySelectorAll("[data-i]").forEach((el) => el.style.setProperty("--i", el.dataset.i));
  root.querySelectorAll("[data-p]").forEach((el) => el.style.setProperty("--p", el.dataset.p));
  root.querySelectorAll("[data-w]").forEach((el) => { el.style.width = `${el.dataset.w}%`; });
}

function seriesUrl(id, qs) {
  return id === null ? `/api/comics?${qs}` : `/api/series/${id}?${qs}`;
}

async function renderSeries(token, id, params) {
  const query = params.get("q") || "";
  const variant = params.get("edition") || "";
  const refresh = params.get("refresh") === "1";
  const rlang = params.get("rlang") || storageGet(localStorage, "lire:rlang");
  const steps = t("series.steps").split("|");
  setView(`
    <div class="page">
      <a class="back" href="#/chercher">${ICON.back} ${esc(t("common.back"))}</a>
      <div class="series">
        <div class="series-cover"><div class="cover skel"></div></div>
        <div>
          <div class="skel skel-title"></div>
          <div class="skel skel-sub"></div>
          <p class="loading-line">${spinner}<span id="load-step">${esc(steps[0])}</span></p>
          <div class="skel-shelf" aria-hidden="true">${Array.from({ length: 24 }, (_, i) => `<i data-i="${i}"></i>`).join("")}</div>
        </div>
      </div>
    </div>`, { nav: "home" });
  applyStagger(main);
  let step = 0;
  const stepTimer = setInterval(() => {
    const el = document.getElementById("load-step");
    if (!el) return clearInterval(stepTimer);
    step = Math.min(step + 1, steps.length - 1);
    el.textContent = steps[step];
  }, 2600);

  let data;
  try {
    const qs = new URLSearchParams({ q: query });
    if (variant) qs.set("variant", variant);
    if (refresh) qs.set("refresh", "true");
    if (rlang) qs.set("rlang", rlang);
    data = await api(seriesUrl(id, qs));
  } finally {
    clearInterval(stepTimer);
  }
  if (token !== renderToken) return;
  drawSeries(token, id, query, data);
}

function seriesHash(id) {
  return id === null ? "#/bd" : `#/serie/${id}`;
}

function synopsisHtml(text, textLang, translating) {
  if (!text) return "";
  return `<p class="synopsis" data-clamped="true" lang="${esc(textLang)}">${esc(text)}</p>
    <p class="translating hint" ${translating ? "" : "hidden"}>${spinner}${esc(t("series.translating"))}</p>
    <button class="link-more" type="button" data-more hidden>${esc(t("series.more"))}</button>`;
}

function wireSynopsis(root) {
  const synopsis = root.querySelector(".synopsis");
  const more = root.querySelector("[data-more]");
  if (!synopsis || !more) return;
  more.hidden = synopsis.scrollHeight <= synopsis.clientHeight + 4 && synopsis.dataset.clamped === "true";
  more.onclick = () => {
    const clamped = synopsis.dataset.clamped === "true";
    synopsis.dataset.clamped = clamped ? "false" : "true";
    more.textContent = t(clamped ? "series.less" : "series.more");
  };
}

/** The local LLM translates in the background: swap the text in when it lands (about a minute at most). */
function followTranslation(token, root, fetcher) {
  let tries = 0;
  const timer = setInterval(async () => {
    if (token !== renderToken || ++tries > 12) return clearInterval(timer);
    if (document.hidden) return;
    try {
      const fresh = await fetcher();
      if (fresh.translating || token !== renderToken) return;
      clearInterval(timer);
      const synopsis = root.querySelector(".synopsis");
      if (synopsis) {
        synopsis.textContent = fresh.synopsis;
        synopsis.lang = fresh.synopsis_lang;
      }
      root.querySelector(".translating")?.setAttribute("hidden", "");
      wireSynopsis(root);
    } catch { clearInterval(timer); }
  }, 6000);
}

function drawSeries(token, id, query, data) {
  const card = data.card;
  const title = data.fr[0] || card.title;
  const subtitle = [card.romaji, card.english].filter((x) => x && x !== title)[0] || "";
  const facts = [card.authors.join(", "), card.year, statusLabel(card.status),
    card.volumes ? t("series.publishedJp", { n: tn(card.volumes, "n.volumePublished") }) : null].filter(Boolean);
  const [headline, sub] = verdict(data);
  const dead = data.shelf.filter((s) => s.state === "dead").map((s) => s.n);
  const deadNote = dead.length ? t("series.deadNote", { vols: humanVolumes(dead) }) : "";
  const editions = data.variants.length > 1
    ? `<div class="block"><h2 class="block-title">${esc(t("series.edition"))}</h2><div class="editions" role="group" aria-label="${esc(t("series.edition"))}">${data.variants.map((v) =>
      `<button type="button" data-edition="${esc(v.name)}" aria-pressed="${v.active}">${esc(variantName(v.name))}<small>${v.volumes}</small></button>`).join("")}</div></div>`
    : "";
  const others = data.others.filter((r) => r.volumes.length);
  const rejected = data.rejected.map(([reason, n]) => `${t(`reject.${reason}`)} (${n})`).join(", ");
  const kavita = data.kavita[0];
  const qsFor = (extra = {}) => {
    const qs = new URLSearchParams({ q: query, rlang: data.lang, ...extra });
    if (data.variant !== "Standard") qs.set("variant", data.variant);
    return qs;
  };
  const languages = data.languages.length
    ? `<div class="block"><h2 class="block-title">${esc(t("series.languages"))}</h2><div class="editions" role="group" aria-label="${esc(t("series.languages"))}">${data.languages.map((l) =>
      `<button type="button" data-rlang="${esc(l.code)}" aria-pressed="${l.code === data.lang}" aria-label="${esc(t(`lang.${l.code}`))}, ${esc(tn(l.volumes, "n.volume"))}">${esc(l.code === "ja" ? "JP" : l.code.toUpperCase())}<small>${l.volumes}</small></button>`).join("")}</div></div>`
    : "";

  setView(`
    <div class="page">
      <a class="back" href="#/chercher">${ICON.back} ${esc(t("common.back"))}</a>
      <div class="series">
        <aside class="series-cover">
          <div class="cover">${coverHtml(card.cover, title)}</div>
          <div class="actionbar-links">
            ${kavita ? `<a class="btn" ${kavitaLink(kavita.url, data.kavita_same_app)}>${data.kavita_same_app ? ICON.book : ICON.open} ${esc(t("series.read"))}</a>` : ""}
            <button class="btn btn-follow" type="button" data-follow aria-pressed="${Boolean(data.follow)}">${ICON.bell} <span>${esc(t(data.follow ? "follow.on" : "follow.off"))}</span></button>
            <p class="hint follow-hint" ${data.follow ? "" : "hidden"}>${esc(followHint(data.follow))}</p>
            <button class="btn btn-quiet" type="button" data-refresh>${ICON.refresh} ${esc(t("series.refresh"))}</button>
          </div>
        </aside>
        <article>
          <header class="series-head">
            <h1 class="series-title">${esc(title)}</h1>
            ${subtitle ? `<p class="series-sub">${esc(subtitle)}</p>` : ""}
            <p class="facts">${facts.map((f) => `<span>${esc(f)}</span>`).join("")}</p>
            ${synopsisHtml(data.synopsis, data.synopsis_lang, data.translating)}
          </header>
          ${languages}
          ${editions}
          <section class="block" aria-labelledby="h-shelf">
            <h2 class="block-title" id="h-shelf">${esc(t("series.shelf"))} <small>${esc(tn(data.counts.horizon, "n.volume"))}</small></h2>
            ${data.shelf.length ? shelfHtml(data) : `<div class="empty"><strong>${esc(t("series.noVolumes"))}</strong><span>${esc(t("series.noVolumesHint"))}</span></div>`}
            <p class="verdict">${esc(headline)}</p>
            <p class="verdict-sub">${esc(sub + deadNote)}</p>
          </section>
          <form id="grab-form">
            ${data.plan.picks.length ? `
              <section class="block" aria-labelledby="h-plan">
                <h2 class="block-title" id="h-plan">${esc(t("series.picks"))} <small>${esc(t("series.picksHint"))}</small></h2>
                <div class="releases">${data.plan.picks.map((r) => releaseRow(r, { checked: true })).join("")}</div>
              </section>` : ""}
            ${others.length ? `
              <details class="more">
                <summary><span>${esc(t("series.others"))} <span class="hint">(${others.length})</span></span>${ICON.chevron}</summary>
                <p class="note">${esc(t("series.othersHint"))}${rejected ? ` ${esc(t("series.rejected", { list: rejected }))}` : ""}</p>
                <div class="releases">${others.map((r) => releaseRow(r, { disabled: r.state !== "available" })).join("")}</div>
              </details>` : ""}
            <div class="actionbar">
              <div class="actionbar-text"><strong id="ab-title"></strong><span id="ab-sub"></span></div>
              <button class="btn btn-primary" type="submit" id="ab-go">${ICON.down} ${esc(t("series.download"))}</button>
            </div>
          </form>
        </article>
      </div>
    </div>`, { nav: "home" });
  applyStagger(main);
  wireSynopsis(main);
  if (data.translating) followTranslation(token, main, () => api(seriesUrl(id, qsFor())));

  main.querySelectorAll("[data-edition]").forEach((btn) => btn.addEventListener("click", () => {
    location.hash = `${seriesHash(id)}?${new URLSearchParams({ q: query, rlang: data.lang, edition: btn.dataset.edition })}`;
  }));
  main.querySelectorAll("[data-rlang]").forEach((btn) => btn.addEventListener("click", () => {
    storageSet(localStorage, "lire:rlang", btn.dataset.rlang);
    location.hash = `${seriesHash(id)}?${new URLSearchParams({ q: query, rlang: btn.dataset.rlang })}`;
  }));
  const followBtn = main.querySelector("[data-follow]");
  followBtn.addEventListener("click", async () => {
    followBtn.disabled = true;
    try {
      if (data.follow) {
        await api(`/api/follows/${data.follow.id}`, { method: "DELETE" });
        data.follow = null;
        toast(t("follow.removed"));
      } else {
        const res = await api("/api/follows", { method: "POST", body: {
          kind: data.kind, ref: String(data.card.id), query, lang: data.lang,
          variant: data.variant === "Standard" ? "" : data.variant } });
        data.follow = res.follow;
        toast(followHint(data.follow));
      }
      followBtn.setAttribute("aria-pressed", String(Boolean(data.follow)));
      followBtn.querySelector("span").textContent = t(data.follow ? "follow.on" : "follow.off");
      const hint = main.querySelector(".follow-hint");
      hint.hidden = !data.follow;
      hint.textContent = followHint(data.follow);
    } catch (err) {
      if (!(err instanceof AuthError)) toast(err.message, true);
    } finally {
      followBtn.disabled = false;
    }
  });
  main.querySelector("[data-refresh]").addEventListener("click", () => {
    const qs = new URLSearchParams({ q: query, rlang: data.lang, refresh: "1" });
    if (data.variant !== "Standard") qs.set("edition", data.variant);
    location.hash = `${seriesHash(id)}?${qs}`;
  });

  const form = main.querySelector("#grab-form");
  const abTitle = main.querySelector("#ab-title");
  const abSub = main.querySelector("#ab-sub");
  const go = main.querySelector("#ab-go");

  function updateBar() {
    const boxes = [...form.querySelectorAll('input[name="rel"]:checked:not(:disabled)')];
    const vols = boxes.flatMap((b) => b.dataset.vols.split(",").filter(Boolean).map(Number)).filter((n) => n >= 1);
    const size = boxes.reduce((sum, b) => sum + Number(b.dataset.size || 0), 0);
    if (!boxes.length) {
      abTitle.textContent = data.plan.picks.length ? t("series.noneSelected") : headline;
      abSub.textContent = data.plan.picks.length ? t("series.tickOne") : t("series.nothingToStart");
      go.disabled = true;
      return;
    }
    abTitle.textContent = humanVolumes(vols) || tn(boxes.length, "n.release");
    abSub.textContent = `${tn(boxes.length, "n.torrent")} · ${fmtSize(size)}`;
    go.disabled = false;
  }
  form.addEventListener("change", updateBar);
  updateBar();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const keys = [...form.querySelectorAll('input[name="rel"]:checked:not(:disabled)')].map((b) => b.value);
    if (!keys.length) return;
    go.disabled = true;
    go.innerHTML = `${spinner} ${esc(t("series.sending"))}`;
    try {
      const res = await api(id === null ? `/api/comics/${data.slug}/grab` : `/api/series/${id}/grab`, { method: "POST", body: { keys, lang: data.lang } });
      const bits = [];
      if (res.added.length) bits.push(tn(res.added.length, "n.started"));
      if (res.skipped.length) bits.push(tn(res.skipped.length, "n.present"));
      if (res.moved) bits.push(t("grab.moved", { torrents: tn(res.moved, "n.torrentFiled"), folder: res.folder }));
      if (bits.length) toast(`${bits.join(", ")}.`);
      for (const e of res.errors) toast(t("grab.error", { title: e.title || t("grab.unknown"), error: e.error }), true);
      refreshBadge();
      const fresh = await api(seriesUrl(id, qsFor()));
      if (token === renderToken) drawSeries(token, id, query, fresh);
    } catch (err) {
      if (err instanceof AuthError) return;
      toast(err.message, true);
      go.disabled = false;
      go.innerHTML = `${ICON.down} ${esc(t("series.download"))}`;
    }
  });
}

/* ---------- Downloads ---------- */

function downloadRow(g) {
  const finished = g.progress >= 1;
  const importing = g.status === "importing";
  const live = !finished && g.speed > 0;
  const pct = Math.floor(g.progress * 100);
  const detail = live ? [fmtSpeed(g.speed), fmtEta(g.eta)].filter(Boolean).join(" · ") : "";
  const side = finished
    ? `<strong>${esc(fmtSize(g.size))}</strong>`
    : `<strong>${pct} %</strong>${esc(detail || fmtSize(g.size))}`;
  const items = g.items.length > 1
    ? `<details><summary>${esc(tn(g.items.length, "n.torrent"))}</summary><div class="dl-items">${g.items.map((i) =>
      `<div class="dl-item"><span>${esc(i.name)}</span><span>${i.state === "done" ? esc(t("dl.status.done")) : `${Math.floor(i.progress * 100)} % · ${esc(t(`dl.status.${i.state}`))}`}</span></div>`).join("")}</div></details>`
    : "";
  const dot = importing ? " live" : live ? " live" : finished ? " done" : "";
  return `
    <div class="dl-row" data-folder="${esc(g.folder)}">
      <div>
        <div class="dl-name">${esc(g.folder)}</div>
        <div class="dl-status"><span class="dot${dot}" aria-hidden="true"></span>${esc(t(`dl.status.${g.status}`))}${!finished && !live ? `<span>· ${esc(fmtSize(g.size))}</span>` : ""}</div>
      </div>
      <div class="dl-side">${side}</div>
      <div class="bar${finished ? " done" : ""}" role="progressbar" aria-label="${esc(g.folder)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><span data-p="${Number(g.progress) || 0}"></span></div>
      ${items}
    </div>`;
}

function followHint(f) {
  if (!f) return "";
  return f.baseline ? t("follow.hint", { n: f.baseline }) : t("follow.hintAll");
}

const relTime = (ts) => {
  const fmt = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  const min = Math.round((ts * 1000 - Date.now()) / 60000);
  if (Math.abs(min) < 60) return fmt.format(min, "minute");
  const h = Math.round(min / 60);
  return Math.abs(h) < 48 ? fmt.format(h, "hour") : fmt.format(Math.round(h / 24), "day");
};

function followStatus(f) {
  const r = f.last_result;
  const bits = [t("follow.after", { n: f.baseline })];
  if (!r) bits.push(t("follow.never"));
  else {
    bits.push(t("follow.checked", { ago: relTime(r.at) }));
    if (r.error) bits.push(t("follow.error"));
    else if (r.grabbed.length) bits.push(t("follow.grabbed", { vols: humanVolumes(r.grabbed) }));
    else if (!r.review.length) bits.push(t("follow.nothing"));
  }
  const review = r?.review?.length
    ? `<div class="follow-review">${r.review.map((x) => esc(t("follow.review", { vols: humanVolumes(x.volumes), title: x.title }))).join("<br>")}</div>`
    : "";
  return { line: bits.join(" · "), review };
}

function followRow(f) {
  const { line, review } = followStatus(f);
  const badge = f.lang && f.lang !== "fr" ? ` <span class="tag">${esc(f.lang === "ja" ? "JP" : f.lang.toUpperCase())}</span>` : "";
  const href = f.kind === "comics" ? `#/bd?${new URLSearchParams({ q: f.query || f.ref, rlang: f.lang })}` : `#/serie/${f.ref}?${new URLSearchParams({ q: f.query || "", rlang: f.lang })}`;
  return `
    <div class="dl-row user-row follow-row">
      <div>
        <div class="dl-name"><a href="${esc(href)}">${esc(f.title)}</a>${badge}</div>
        <div class="dl-status">${esc(line)}</div>
        ${review}
      </div>
      <div class="user-actions">
        <button class="btn btn-small" type="button" data-check="${f.id}">${esc(t("follow.check"))}</button>
        <button class="btn btn-small btn-quiet" type="button" data-unfollow="${f.id}">${esc(t("follow.stop"))}</button>
      </div>
    </div>`;
}

async function renderFollows(token, box) {
  const data = await api("/api/follows");
  if (token !== renderToken) return;
  box.innerHTML = `<div class="section-head section-gap"><h2>${esc(t("follow.title"))}</h2><span class="hint">${esc(tn(data.follows.length, "n.series"))}</span></div>
    ${data.follows.length ? `<div class="dl-list">${data.follows.map(followRow).join("")}</div>` : `<p class="hint">${esc(t("follow.empty"))}</p>`}`;
}

async function renderDownloads(token) {
  setView(`<div class="page"><div class="search-hero"><h1>${esc(t("dl.title"))}</h1></div><div id="dl" class="section">${loadingLine()}</div><div id="follows" class="section"></div></div>`, { nav: "downloads" });
  const box = main.querySelector("#dl");
  const followBox = main.querySelector("#follows");
  renderFollows(token, followBox).catch(() => {});
  followBox.addEventListener("click", async (event) => {
    const check = event.target.closest("[data-check]");
    const stop = event.target.closest("[data-unfollow]");
    const btn = check || stop;
    if (!btn) return;
    btn.disabled = true;
    if (check) btn.innerHTML = spinner;
    try {
      if (check) await api(`/api/follows/${check.dataset.check}/check`, { method: "POST" });
      if (stop) {
        await api(`/api/follows/${stop.dataset.unfollow}`, { method: "DELETE" });
        toast(t("follow.removed"));
      }
      await renderFollows(token, followBox);
      if (check) refreshBadge();
    } catch (err) {
      if (!(err instanceof AuthError)) toast(err.message, true);
      btn.disabled = false;
      if (check) btn.textContent = t("follow.check");
    }
  });
  async function load() {
    const data = await api("/api/downloads");
    if (token !== renderToken) return;
    const open = new Set([...box.querySelectorAll("details[open]")].map((d) => d.closest(".dl-row")?.dataset.folder));
    const active = data.groups.filter(isActive);
    const done = data.groups.filter((g) => !isActive(g));
    let html = "";
    if (!data.groups.length) {
      html = `<div class="empty"><strong>${esc(t("dl.nothing"))}</strong><span>${esc(t("dl.nothingHint"))}</span><a class="btn empty-cta" href="#/chercher">${esc(t("dl.search"))}</a></div>`;
    }
    if (active.length) html += `<div class="section-head"><h2>${esc(t("dl.active"))}</h2><span class="hint">${esc(tn(active.length, "n.series"))}</span></div><div class="dl-list">${active.map(downloadRow).join("")}</div>`;
    if (done.length) html += `<div class="section-head section-gap"><h2>${esc(t("dl.done"))}</h2><span class="hint">${esc(t("dl.doneHint"))}</span></div><div class="dl-list">${done.slice(0, 40).map(downloadRow).join("")}</div>`;
    box.innerHTML = html;
    applyStagger(box);
    box.querySelectorAll(".dl-row").forEach((row) => {
      if (open.has(row.dataset.folder)) row.querySelector("details")?.setAttribute("open", "");
    });
    setBadge(active.length);
  }
  await load();
  poll(token, 4000, load);
}

/* ---------- Library ---------- */

function kavitaLink(url, sameApp) {
  return sameApp ? `href="${esc(url)}"` : `href="${esc(url)}" target="_blank" rel="noopener"`;
}

function progressLabel(p) {
  if (!p || p.status === "new") return t("progress.new");
  if (p.status === "done") return t("progress.done");
  return p.volume ? t("progress.volume", { v: p.volume, page: p.page, pages: p.pages }) : t("progress.page", { page: p.page, pages: p.pages });
}

function libraryCard(s, { manage = false } = {}) {
  const pct = s.pages ? Math.min(100, (100 * s.read) / s.pages) : 0;
  const badge = s.lang ? `<span class="lang-badge" aria-label="${esc(t(`lang.${s.lang}`))}">${esc(s.lang === "ja" ? "JP" : s.lang.toUpperCase())}</span>` : "";
  const inner = `<div class="cover"><img src="${esc(s.cover)}" alt="" loading="lazy" decoding="async">${badge}${pct > 0 ? `<div class="cover-progress"><span data-w="${pct.toFixed(1)}"></span></div>` : ""}</div><div class="cover-title">${esc(s.name)}</div><div class="cover-meta">${esc(progressLabel(s.progress))}</div>`;
  if (manage) {
    return `<div class="cover-link managed">${inner}<button class="cover-delete" type="button" data-delete="${s.id}" data-kind="${esc(s.kind || "manga")}" data-lang="${esc(s.lang || "")}" data-name="${esc(s.name)}" aria-label="${esc(t("lib.deleteLabel", { name: s.name }))}">${ICON.trash}</button></div>`;
  }
  return `<button class="cover-link cover-button" type="button" data-open="${s.id}" data-kind="${esc(s.kind || "manga")}" aria-label="${esc(s.name)}, ${esc(progressLabel(s.progress))}">${inner}</button>`;
}

function volumeName(v) {
  return v.number !== null ? t("detail.volumeN", { n: v.number }) : (v.name && v.name !== "0" ? v.name : t("detail.special"));
}

async function loadVolumes(id, box) {
  let data;
  try { data = await api(`/api/library/${id}/volumes`); } catch { return; }
  if (!data.volumes.length) return;
  const grid = box.querySelector(".vol-grid");
  const panel = box.querySelector(".vol-panel");
  grid.innerHTML = data.volumes.map((v, i) => {
    const state = v.pages && v.read >= v.pages ? "done" : v.read > 0 ? "reading" : "new";
    const label = v.number !== null ? v.number : "HS";
    return `<button type="button" role="listitem" class="vol" data-i="${i}" data-state="${state}" aria-pressed="false" aria-label="${esc(volumeName(v))}, ${esc(tn(v.pages, "n.page"))}">${esc(String(label))}</button>`;
  }).join("");
  box.hidden = false;

  function show(i) {
    const v = data.volumes[i];
    grid.querySelectorAll(".vol").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.i === String(i))));
    const start = v.read > 0 && v.read < v.pages ? v.read + 1 : 1;
    panel.innerHTML = `
      <div class="vol-head"><strong>${esc(volumeName(v))}</strong><span class="hint">${esc(tn(v.pages, "n.page"))}</span></div>
      <label class="vol-range"><span class="visually-hidden">${esc(t("detail.pagePick"))}</span>
        <input type="range" min="1" max="${Math.max(1, v.pages)}" value="${start}" step="1">
        <output>${esc(t("detail.pageOf", { n: start, total: v.pages }))}</output></label>
      <div class="detail-actions">
        <button class="btn btn-primary" type="button" data-go>${ICON.book} <span>${esc(t("detail.readFrom", { n: start }))}</span></button>
        <button class="btn" type="button" data-start>${esc(t("detail.fromStart"))}</button>
      </div>`;
    panel.hidden = false;
    const range = panel.querySelector("input");
    const out = panel.querySelector("output");
    const goLabel = panel.querySelector("[data-go] span");
    range.addEventListener("input", () => {
      out.textContent = t("detail.pageOf", { n: range.value, total: v.pages });
      goLabel.textContent = t("detail.readFrom", { n: range.value });
    });
    const open = async (page, btn) => {
      btn.disabled = true;
      try {
        const res = await api(`/api/library/${id}/open`, { method: "POST", body: { volumeId: v.volumeId, page } });
        location.href = res.url;
      } catch (err) {
        if (!(err instanceof AuthError)) toast(err.message, true);
        btn.disabled = false;
      }
    };
    panel.querySelector("[data-go]").addEventListener("click", (e) => open(Number(range.value), e.currentTarget));
    panel.querySelector("[data-start]").addEventListener("click", (e) => open(1, e.currentTarget));
  }
  grid.addEventListener("click", (event) => {
    const btn = event.target.closest(".vol");
    if (btn) show(Number(btn.dataset.i));
  });
}

async function openDetails(id, kind = "manga") {
  const token = renderToken;
  const dialog = document.createElement("dialog");
  dialog.className = "sheet sheet-detail";
  dialog.innerHTML = `<div class="detail">${loadingLine()}</div>`;
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  dialog.showModal();
  const fetcher = () => api(`/api/library/${id}/details?kind=${encodeURIComponent(kind)}`);
  try {
    const d = await fetcher();
    const p = d.progress;
    const where = p.status === "reading"
      ? (p.volume ? t("detail.where", { page: p.page, v: p.volume }) : t("detail.wherePage", { page: p.page }))
      : t(p.status === "done" ? "detail.allRead" : "detail.notStarted");
    const action = t(p.status === "reading" ? "detail.resume" : p.status === "done" ? "detail.reread" : "detail.start");
    const facts = [d.authors?.join(", "), d.year, statusLabel(d.status), d.volumes ? tn(d.volumes, "n.volumePublished") : null].filter(Boolean);
    const pct = p.pages ? Math.min(1, p.page / p.pages) : 0;
    dialog.innerHTML = `
      <div class="detail">
        <button class="detail-close" type="button" aria-label="${esc(t("common.close"))}">×</button>
        <div class="detail-cover cover"><img src="${esc(d.cover)}" alt=""></div>
        <div class="detail-body">
          <h2>${esc(d.title)}</h2>
          ${d.title !== d.name ? `<p class="series-sub">${esc(d.name)}</p>` : ""}
          ${facts.length ? `<p class="facts">${facts.map((f) => `<span>${esc(f)}</span>`).join("")}</p>` : ""}
          <div class="detail-progress">
            <strong>${esc(where)}</strong>
            ${p.status === "reading" ? `<div class="bar"><span data-p="${pct}"></span></div>` : ""}
          </div>
          <div class="detail-actions">
            ${p.read_url ? `<a class="btn btn-primary" href="${esc(p.read_url)}">${ICON.book} ${esc(action)}</a>` : ""}
            <a class="btn" href="${esc(d.url)}">${esc(t("detail.kavita"))}</a>
            ${p.status !== "new" ? `<button class="btn btn-quiet" type="button" data-reset>${esc(t("progress.resetShort"))}</button>` : ""}
          </div>
          <section class="vol-picker" aria-labelledby="h-vols" hidden>
            <h3 class="block-title" id="h-vols">${esc(t("detail.volumes"))}</h3>
            <div class="vol-grid" role="list"></div>
            <div class="vol-panel" hidden></div>
          </section>
          ${d.synopsis ? `<p class="synopsis detail-synopsis" lang="${esc(d.synopsis_lang)}">${esc(d.synopsis)}</p>
            <p class="translating hint" ${d.translating ? "" : "hidden"}>${spinner}${esc(t("series.translating"))}</p>` : ""}
        </div>
      </div>`;
    applyStagger(dialog);
    dialog.querySelector(".detail-close").addEventListener("click", () => dialog.close());
    dialog.querySelector("[data-reset]")?.addEventListener("click", async () => {
      if (!(await resetProgress(id, d.name))) return;
      dialog.close();
      if (token === renderToken) route();
    });
    if (d.translating) followTranslation(token, dialog, fetcher);
    loadVolumes(id, dialog.querySelector(".vol-picker"));
  } catch (err) {
    if (err instanceof AuthError) { dialog.close(); return; }
    dialog.innerHTML = `<div class="detail">${errorBox(err.message)}</div>`;
  }
}

document.addEventListener("click", (event) => {
  const card = event.target.closest("[data-open]");
  if (card) openDetails(Number(card.dataset.open), card.dataset.kind || "manga");
});

function confirmDialog({ title, body, confirm, danger = false }) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "sheet";
    dialog.innerHTML = `
      <form method="dialog" class="sheet-body">
        <h2>${esc(title)}</h2>
        <p>${esc(body)}</p>
        <div class="sheet-actions">
          <button class="btn" value="cancel" type="submit">${esc(t("common.cancel"))}</button>
          <button class="btn ${danger ? "btn-danger" : "btn-primary"}" value="ok" type="submit">${esc(confirm)}</button>
        </div>
      </form>`;
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "ok");
      dialog.remove();
    }, { once: true });
    dialog.showModal();
    dialog.querySelector('[value="cancel"]').focus();
  });
}

function continueCard(s) {
  const pct = s.pages ? Math.min(100, (100 * s.read) / s.pages) : 0;
  const badge = s.lang ? `<span class="lang-badge">${esc(s.lang === "ja" ? "JP" : s.lang.toUpperCase())}</span>` : "";
  const cover = `<div class="cover"><img src="${esc(s.cover)}" alt="" loading="lazy" decoding="async">${badge}<div class="cover-progress"><span data-w="${pct.toFixed(1)}"></span></div></div>`;
  const text = `<div class="cover-title">${esc(s.name)}</div><div class="cover-meta">${esc(progressLabel(s.progress))}</div>`;
  const open = s.progress?.read_url
    ? `<a class="cover-link" href="${esc(s.progress.read_url)}" aria-label="${esc(t("detail.resume"))} ${esc(s.name)}, ${esc(progressLabel(s.progress))}">${cover}${text}</a>`
    : `<button class="cover-link cover-button" type="button" data-open="${s.id}" data-kind="${esc(s.kind)}">${cover}${text}</button>`;
  return `<div class="continue-item">${open}<button class="cover-delete continue-remove" type="button" data-unread="${s.id}" data-name="${esc(s.name)}" aria-label="${esc(t("progress.resetTitle", { name: s.name }))}">×</button></div>`;
}

async function resetProgress(id, name) {
  const ok = await confirmDialog({ title: t("progress.resetTitle", { name }), body: t("progress.resetBody"), confirm: t("common.remove") });
  if (!ok) return false;
  try {
    await api(`/api/library/${id}/progress`, { method: "DELETE" });
    toast(t("progress.resetDone", { name }));
    return true;
  } catch (err) {
    if (!(err instanceof AuthError)) toast(err.message, true);
    return false;
  }
}

async function loadContinue(token, box) {
  try {
    const data = await api("/api/continue");
    if (token !== renderToken || !data.series.length) return;
    box.innerHTML = `<div class="section-head"><h2 id="h-continue">${esc(t("lib.continue"))}</h2></div><div class="rail">${data.series.map(continueCard).join("")}</div>`;
    box.hidden = false;
    applyStagger(box);
    box.onclick = async (event) => {
      const btn = event.target.closest("[data-unread]");
      if (!btn || !(await resetProgress(btn.dataset.unread, btn.dataset.name))) return;
      btn.closest(".continue-item").remove();
      if (!box.querySelector(".continue-item")) box.hidden = true;
    };
  } catch { /* reading progress is a bonus, the library still works */ }
}

async function renderLibrary(token, { manage = false, kind = "manga" } = {}) {
  const tabs = `<div class="editions lib-tabs" role="tablist" aria-label="${esc(t("lib.title"))}">
    <a role="tab" href="#/" aria-selected="${kind === "manga"}">${esc(t("home.mangas"))}</a>
    <a role="tab" href="#/bibliotheque?type=bd" aria-selected="${kind === "comics"}">${esc(t("home.comics"))}</a></div>`;
  setView(`<div class="page"><section class="section continue" id="lib-continue" aria-labelledby="h-continue" hidden></section><div class="search-hero lib-head"><div><h1>${esc(t("lib.title"))}</h1>${tabs}<p class="hint" id="lib-hint"></p></div><div id="lib-tools"></div></div><p class="notice notice-quiet" id="lib-link" hidden></p><p class="notice" id="lib-importing" hidden></p><div id="lib" class="section">${loadingLine()}</div></div>`, { nav: "library" });
  linkKavitaFromSession().then(() => {
    const note = main.querySelector("#lib-link");
    if (!note || me.kavitaLinked || token !== renderToken) return;
    note.innerHTML = `${esc(t("lib.linkKavita"))} <a href="/kavita/">${esc(t("lib.openKavita"))}</a>`;
    note.hidden = false;
  });
  const box = main.querySelector("#lib");
  const tools = main.querySelector("#lib-tools");
  const hint = main.querySelector("#lib-hint");
  const notice = main.querySelector("#lib-importing");
  let data = { series: [], can_delete: false };
  let signature = null;

  function draw() {
    hint.textContent = t(manage ? "lib.manageHint" : "lib.hint");
    tools.innerHTML = data.can_delete && data.series.length
      ? `<button class="btn${manage ? " btn-on" : ""}" type="button" id="manage" aria-pressed="${manage}">${esc(t(manage ? "lib.doneManaging" : "lib.manage"))}</button>`
      : "";
    box.innerHTML = data.series.length
      ? `<div class="covers">${data.series.map((s) => libraryCard(s, { manage })).join("")}</div>`
      : `<div class="empty"><strong>${esc(t("lib.empty"))}</strong><span>${esc(t("lib.emptyHint"))}</span><a class="btn empty-cta" href="#/chercher">${esc(t("dl.search"))}</a></div>`;
    applyStagger(box);
    tools.querySelector("#manage")?.addEventListener("click", () => { manage = !manage; draw(); });
  }

  /* Downloads that finished but Kavita has not indexed yet: say so, and refresh until they land. */
  async function load() {
    const [lib, dls] = await Promise.all([api(`/api/library?kind=${kind}`), api("/api/downloads").catch(() => ({ groups: [] }))]);
    if (token !== renderToken) return;
    lib.series.forEach((s) => { s.kind = kind; });
    const importing = dls.groups.filter((g) => g.status === "importing" && g.kind === kind).map((g) => g.folder);
    notice.hidden = !importing.length;
    notice.innerHTML = importing.length ? `${spinner}${esc(t("lib.importing", { names: importing.join(", ") }))}` : "";
    const next = lib.series.map((s) => `${s.id}:${s.read}:${s.cover}`).join("|");
    data = lib;
    if (next !== signature && !(manage && signature)) {
      signature = next;
      draw();
    }
    if (importing.length && !pollTimer) poll(token, 15000, load);
    if (!importing.length && pollTimer) stopPolling();
  }

  loadContinue(token, main.querySelector("#lib-continue"));

  box.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-delete]");
    if (!btn) return;
    const id = Number(btn.dataset.delete);
    const name = btn.dataset.name;
    const ok = await confirmDialog({ title: t("lib.deleteTitle", { name }), body: t("lib.deleteBody"), confirm: t("common.delete"), danger: true });
    if (!ok) return;
    btn.disabled = true;
    btn.innerHTML = spinner;
    try {
      const res = await api(`/api/admin/library/${id}?${new URLSearchParams({ kind: btn.dataset.kind || "manga", lang: btn.dataset.lang || "" })}`, { method: "DELETE" });
      toast(res.freed ? t("lib.deletedFreed", { name: res.name, size: fmtSize(res.freed) }) : t("lib.deleted", { name: res.name }));
      data.series = data.series.filter((s) => s.id !== id);
      draw();
    } catch (err) {
      if (err instanceof AuthError) return;
      toast(err.message, true);
      btn.disabled = false;
      btn.innerHTML = ICON.trash;
    }
  });
  await load();
}

/* ---------- Accounts (admin) ---------- */

async function renderAccounts(token) {
  setView(`
    <div class="page">
      <div class="search-hero"><h1>${esc(t("acc.title"))}</h1><p class="hint">${esc(t("acc.hint"))}</p></div>
      <form class="add-user" id="add-user" autocomplete="off">
        <label class="visually-hidden" for="new-user">${esc(t("acc.newLabel"))}</label>
        <input class="input" id="new-user" placeholder="${esc(t("acc.newPlaceholder"))}" autocapitalize="none" autocorrect="off" spellcheck="false" maxlength="31" required>
        <button class="btn btn-primary" type="submit">${esc(t("acc.create"))}</button>
      </form>
      <div id="new-cred" aria-live="polite"></div>
      <div id="users" class="section">${loadingLine()}</div>
    </div>`, { nav: "accounts" });
  const list = main.querySelector("#users");
  const cred = main.querySelector("#new-cred");

  function showCredentials(res, title) {
    const link = res.sso_link ? `<div><dt>${esc(t("acc.ssoLink"))}</dt><dd class="mono">${esc(res.sso_link)}</dd></div>` : "";
    const password = res.password ? `<div><dt>${esc(t("acc.fallback"))}</dt><dd class="mono">${esc(res.password)}</dd></div>` : "";
    cred.innerHTML = `
      <div class="cred" role="status">
        <strong>${esc(title)}</strong>
        <p>${esc(t(res.sso_link ? "acc.ssoShare" : "acc.shareOnce"))}</p>
        <dl>
          <div><dt>${esc(t("acc.address"))}</dt><dd>${esc(location.origin)}</dd></div>
          <div><dt>${esc(t("login.user"))}</dt><dd>${esc(res.username)}</dd></div>
          ${link}${password}
        </dl>
        <p class="hint">${esc(res.sso_note || res.kavita_note || t(res.sso_link ? "acc.ssoHint" : "acc.sameKavita"))}</p>
        <button class="btn" type="button" id="copy-cred">${esc(t("acc.copy"))}</button>
      </div>`;
    cred.querySelector("#copy-cred").addEventListener("click", async () => {
      const lines = [t("acc.msgUrl", { url: location.origin })];
      if (res.sso_link) lines.push(t("acc.msgLink", { link: res.sso_link, name: me.oidc?.name || "SSO" }));
      lines.push(t("acc.msgUser", { user: res.username }));
      if (res.password) lines.push(t("acc.msgPassword", { password: res.password }));
      const text = lines.join("\n");
      try { await navigator.clipboard.writeText(text); toast(t("acc.copied")); } catch { toast(t("acc.copyFailed"), true); }
    });
  }

  async function load() {
    const data = await api("/api/admin/users");
    if (token !== renderToken) return;
    list.innerHTML = `<div class="dl-list">${data.users.map((u) => `
      <div class="dl-row user-row">
        <div>
          <div class="dl-name">${esc(u.username)}${u.role === "admin" ? ` <span class="tag good">${esc(t("acc.admin"))}</span>` : ""}</div>
          <div class="dl-status">${esc(tn(u.grabs, "n.started"))} · ${esc(t("acc.since", { date: date(u.created_at * 1000) }))}</div>
        </div>
        <div class="user-actions">${me.oidc?.accounts ? `<button class="btn btn-small" type="button" data-sso="${u.id}" data-name="${esc(u.username)}">${esc(t("acc.ssoButton"))}</button>` : ""}${u.role === "admin" ? "" : `
          <button class="btn btn-small btn-quiet" type="button" data-reset="${u.id}" data-name="${esc(u.username)}">${esc(t("acc.reset"))}</button>
          <button class="btn btn-small btn-quiet" type="button" data-remove="${u.id}" data-name="${esc(u.username)}">${esc(t("common.delete"))}</button>`}
        </div>
      </div>`).join("")}</div>`;
  }

  main.querySelector("#add-user").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = main.querySelector("#new-user");
    const button = event.target.querySelector("button");
    button.disabled = true;
    try {
      const res = await api("/api/admin/users", { method: "POST", body: { username: input.value.trim().toLowerCase() } });
      input.value = "";
      showCredentials(res, t("acc.created", { name: res.username }));
      await load();
    } catch (err) {
      if (!(err instanceof AuthError)) toast(err.message, true);
    } finally {
      button.disabled = false;
    }
  });

  list.addEventListener("click", async (event) => {
    const reset = event.target.closest("[data-reset]");
    const remove = event.target.closest("[data-remove]");
    const sso = event.target.closest("[data-sso]");
    try {
      if (sso) {
        sso.disabled = true;
        const res = await api(`/api/admin/users/${sso.dataset.sso}/sso-link`, { method: "POST" });
        showCredentials(res, t("acc.ssoTitle", { name: sso.dataset.name }));
        sso.disabled = false;
        cred.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      if (reset) {
        const name = reset.dataset.name;
        const ok = await confirmDialog({ title: t("acc.resetTitle", { name }), body: t("acc.resetBody"), confirm: t("acc.generate") });
        if (!ok) return;
        showCredentials(await api(`/api/admin/users/${reset.dataset.reset}/password`, { method: "POST" }), t("acc.newPassword", { name }));
      }
      if (remove) {
        const name = remove.dataset.name;
        const ok = await confirmDialog({ title: t("acc.removeTitle", { name }), body: t("acc.removeBody"), confirm: t("common.delete"), danger: true });
        if (!ok) return;
        await api(`/api/admin/users/${remove.dataset.remove}`, { method: "DELETE" });
        toast(t("acc.removed", { name }));
        await load();
      }
    } catch (err) {
      if (!(err instanceof AuthError)) toast(err.message, true);
    }
  });
  await load();
}

/* ---------- Badge ---------- */

function setBadge(n) {
  badge.hidden = !n;
  badge.textContent = n ? String(n) : "";
}

async function refreshBadge() {
  try {
    const data = await api("/api/downloads");
    setBadge(data.groups.filter(isActive).length);
  } catch { /* the badge is best effort */ }
}

/* ---------- Boot ---------- */

translateDom();
syncLangButton();
document.getElementById("lang").addEventListener("click", switchLang);
window.addEventListener("hashchange", route);
main.addEventListener("error", (event) => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement) || img.dataset.failed) return;
  img.dataset.failed = "1";
  const fallback = document.createElement("span");
  fallback.className = "cover-fallback";
  fallback.textContent = img.closest(".cover-link")?.querySelector(".cover-title")?.textContent || "";
  img.replaceWith(fallback);
}, true);
document.getElementById("logout").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST" }); } catch { /* the cookie is gone either way */ }
  me.username = "";
  me.role = "";
  renderLogin();
});
(async () => {
  try {
    if (!(await loadSession())) return renderLogin();
  } catch {
    return renderLogin();
  }
  if (new URLSearchParams(location.search).has("signed")) history.replaceState(null, "", location.pathname + location.hash);
  await linkKavitaFromSession();
  route();
  refreshBadge();
  setInterval(() => { if (!document.hidden) refreshBadge(); }, 30000);
})();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {}));
}
