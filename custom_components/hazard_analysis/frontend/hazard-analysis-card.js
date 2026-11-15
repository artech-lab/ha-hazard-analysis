/*
 * Hazard Analysis Card for Home Assistant
 * https://github.com/artech-lab/ha-hazard-analysis
 *
 * Dashboard card bundled with the Hazard Analysis integration, which serves
 * and loads it automatically (no dashboard resource needed). It only displays
 * what the integration computes: overall risk, AI summary, recommended
 * action, per-category severity, de-escalation state, confidence and
 * freshness of the analysis, plus a button for a new analysis. Every entity
 * is discovered from the device of the configured risk level sensor.
 *
 * One dependency-free file, no build step. Localized: English and Italian.
 *
 * Copyright (C) 2026 The ha-hazard-analysis contributors
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the Free
 * Software Foundation, either version 3 of the License, or (at your option)
 * any later version. This program is distributed in the hope that it will be
 * useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
 * Public License for more details: <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

// The integration appends its manifest version to the URL of this module.
const CARD_VERSION = new URL(import.meta.url).searchParams.get("v") || "dev";
const CARD_TAG = "hazard-analysis-card";
const EDITOR_TAG = "hazard-analysis-card-editor";
const INTEGRATION = "hazard_analysis";

const STRINGS = {
  en: {
    card_name: "Hazard Analysis",
    card_description:
      "AI safety monitoring of an area: overall risk, summary, recommended action, severity per category and confidence.",
    default_title: "Area hazards",
    subtitle: "Hazard analysis",
    updated: "Updated {ago}",
    stale: "No analysis for {dur}",
    failed: "Last analysis failed · retrying",
    paused: "Monitoring paused",
    running: "Analysis running…",
    all_clear: "All clear",
    level_none: "None",
    level_low: "Low",
    level_medium: "Medium",
    level_high: "High",
    level_critical: "Critical",
    no_data: "n/a",
    categories: "Hazard categories",
    pending: "de-escalating · awaiting confirmation",
    pending_hint: "A lower reading is waiting for confirmation: levels drop only after two consecutive readings.",
    recommended: "Recommended action",
    confidence: "Confidence",
    confidence_hint: "How clear and complete the evidence behind the analysis is",
    waiting: "Waiting for the first analysis…",
    analyze: "Run a new analysis",
    fire: "Fire",
    smoke: "Smoke",
    flood: "Flood",
    accident: "Accident",
    other: "Other",
    now: "just now",
    min_ago: "{n} min ago",
    h_ago: "{n} h ago",
    d_ago: "{n} d ago",
    no_entity: "Select the risk level sensor of a Hazard Analysis device.",
    // editor
    e_entity: "Risk level sensor",
    e_name: "Title",
    e_show_summary: "Show summary",
    e_show_recommendation: "Show recommended action",
    e_show_confidence: "Show confidence",
    e_show_refresh: "Show the new analysis button"
  },
  it: {
    card_name: "Hazard Analysis",
    card_description:
      "Monitoraggio AI della sicurezza di un'area: rischio complessivo, sintesi, azione consigliata, severità per categoria e affidabilità.",
    default_title: "Rischi dell'area",
    subtitle: "Analisi rischi",
    updated: "Aggiornata {ago}",
    stale: "Analisi ferma da {dur}",
    failed: "Ultima analisi non riuscita · nuovo tentativo",
    paused: "Monitoraggio in pausa",
    running: "Analisi in corso…",
    all_clear: "Tutto sicuro",
    level_none: "Nullo",
    level_low: "Basso",
    level_medium: "Moderato",
    level_high: "Alto",
    level_critical: "Critico",
    no_data: "n/d",
    categories: "Categorie di rischio",
    pending: "in rientro · attesa conferma",
    pending_hint: "Una lettura più bassa è in attesa di conferma: i livelli scendono solo dopo due letture consecutive.",
    recommended: "Azione consigliata",
    confidence: "Affidabilità",
    confidence_hint: "Quanto sono chiari e completi i dati alla base dell'analisi",
    waiting: "In attesa della prima analisi…",
    analyze: "Genera una nuova analisi",
    fire: "Incendio",
    smoke: "Fumo",
    flood: "Allagamento",
    accident: "Incidente",
    other: "Altro",
    now: "adesso",
    min_ago: "{n} min fa",
    h_ago: "{n} h fa",
    d_ago: "{n} g fa",
    no_entity: "Seleziona il sensore livello di rischio di un dispositivo Hazard Analysis.",
    e_entity: "Sensore livello di rischio",
    e_name: "Titolo",
    e_show_summary: "Mostra la sintesi",
    e_show_recommendation: "Mostra l'azione consigliata",
    e_show_confidence: "Mostra l'affidabilità",
    e_show_refresh: "Mostra il pulsante nuova analisi"
  }
};

function langOf(hass) {
  const l = (hass && ((hass.locale && hass.locale.language) || hass.language)) ||
    (typeof navigator !== "undefined" ? navigator.language : "en");
  return String(l || "en").toLowerCase().split("-")[0];
}

function t(hass, key, vars) {
  const table = STRINGS[langOf(hass)] || STRINGS.en;
  let s = table[key] != null ? table[key] : (STRINGS.en[key] != null ? STRINGS.en[key] : key);
  if (vars) for (const k of Object.keys(vars)) s = s.replace("{" + k + "}", vars[k]);
  return s;
}

/* Translation keys of the integration's entities -> roles in the card. */
const ROLES = {
  risk_level: "risk_level",
  fire: "fire",
  smoke: "smoke",
  flood: "flood",
  accident: "accident",
  other: "other",
  confidence: "confidence",
  summary: "summary",
  recommendation: "recommendation",
  last_analysis: "last_analysis",
  hazard: "hazard",
  analyzing: "analyzing",
  deescalation_pending: "deescalation_pending",
  problem: "problem",
  analyze_now: "analyze_now",
  monitoring: "monitoring"
};

const CATEGORIES = [
  { key: "fire", icon: "mdi:fire" },
  { key: "smoke", icon: "mdi:smoke" },
  { key: "flood", icon: "mdi:home-flood" },
  { key: "accident", icon: "mdi:hazard-lights" },
  { key: "other", icon: "mdi:alert-circle-outline" }
];
const LEVELS = ["none", "low", "medium", "high", "critical"];
const SEV_COLORS = [
  "var(--disabled-text-color, #9e9e9e)",
  "var(--yellow-color, #f9a825)",
  "var(--orange-color, #fb8c00)",
  "var(--red-color, #e53935)",
  "var(--deep-red, #b71c1c)"
];
const OK_COLOR = "var(--green-color, #43a047)";
const BAD = new Set(["unknown", "unavailable", ""]);

function findRiskEntity(hass) {
  const reg = (hass && hass.entities) || {};
  for (const id of Object.keys(reg)) {
    const e = reg[id];
    if (e && e.platform === INTEGRATION && e.translation_key === "risk_level") return id;
  }
  return null;
}

function discover(hass, riskEntity) {
  const out = {};
  const reg = (hass && hass.entities) || {};
  const me = reg[riskEntity];
  if (!me || !me.device_id) return out;
  for (const id of Object.keys(reg)) {
    const e = reg[id];
    if (!e || e.device_id !== me.device_id || e.platform !== INTEGRATION) continue;
    const role = ROLES[e.translation_key];
    if (role) out[role] = id;
  }
  return out;
}

async function ensureHaForm() {
  if (customElements.get("ha-form")) return;
  try {
    const helpers = await window.loadCardHelpers();
    const card = await helpers.createCardElement({ type: "entities", entities: [] });
    if (card && card.constructor && card.constructor.getConfigElement) await card.constructor.getConfigElement();
  } catch (e) {
    /* ha-form will be loaded by the edit dialog */
  }
}

const clampLevel = (v) => Math.max(0, Math.min(4, Math.round(parseFloat(v) || 0)));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class HazardAnalysisCard extends HTMLElement {
  static getStubConfig(hass) {
    return { entity: findRiskEntity(hass) || "" };
  }

  static async getConfigElement() {
    await ensureHaForm();
    return document.createElement(EDITOR_TAG);
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = Object.assign(
      { show_summary: true, show_recommendation: true, show_confidence: true, show_refresh: true },
      config,
      { entity: config.entity || "" }
    );
    this._built = false;
    if (this.shadowRoot && this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!this._built) this._render();
    this._update();
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, rows: "auto", min_columns: 6 };
  }

  connectedCallback() {
    clearInterval(this._tick);
    this._tick = setInterval(() => this._built && this._update(), 60000);
  }

  disconnectedCallback() {
    clearInterval(this._tick);
  }

  _t(key, vars) {
    return t(this._hass, key, vars);
  }

  _entities() {
    const found = discover(this._hass, this._config.entity);
    found.risk_level = this._config.entity;
    return found;
  }

  _st(id) {
    return id && this._hass ? this._hass.states[id] : undefined;
  }

  _more(id) {
    if (!id) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: id }, bubbles: true, composed: true }));
  }

  _ago(sec) {
    if (sec < 90) return this._t("now");
    if (sec < 3600) return this._t("min_ago", { n: Math.round(sec / 60) });
    if (sec < 86400) return this._t("h_ago", { n: Math.round(sec / 3600) });
    return this._t("d_ago", { n: Math.round(sec / 86400) });
  }

  _dur(sec) {
    if (sec < 3600) return Math.round(sec / 60) + " min";
    if (sec < 86400) {
      const h = Math.floor(sec / 3600);
      const m = Math.round((sec % 3600) / 60);
      return m ? `${h} h ${m} min` : `${h} h`;
    }
    return Math.round(sec / 86400) + (langOf(this._hass) === "it" ? " g" : " d");
  }

  _render() {
    const c = this._config;
    if (!this._hass) return;
    this._built = true;
    const title = esc(c.name || this._t("default_title"));
    this.shadowRoot.innerHTML = `
<style>
  :host { display: block; height: 100%; }
  ha-card { position: relative; overflow: hidden; height: 100%; box-sizing: border-box; display: flex;
    flex-direction: column; padding: 14px 16px 12px; --hz: ${OK_COLOR}; }
  .head { display: flex; align-items: center; gap: 12px; padding-bottom: 6px; cursor: pointer; }
  .shape { width: 40px; height: 40px; min-width: 40px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; color: var(--hz); background: color-mix(in srgb, var(--hz) 20%, transparent);
    transition: background .4s, color .4s; }
  .head:hover .shape { background: color-mix(in srgb, var(--hz) 30%, transparent); }
  .shape ha-icon { --mdc-icon-size: 22px; }
  .tt { flex: 1; min-width: 0; }
  .title { font-size: 1rem; font-weight: 500; line-height: 1.3; color: var(--primary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { font-size: .8rem; line-height: 1.3; color: var(--secondary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: color .3s; }
  .sub.warn { color: var(--warning-color, #ffa726); }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600;
    padding: 4px 10px; border-radius: 999px; white-space: nowrap; color: var(--hz);
    background: color-mix(in srgb, var(--hz) 15%, transparent); transition: color .4s, background .4s; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--hz); box-shadow: 0 0 6px var(--hz); }
  .pill.alert .dot { animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--hz) 60%, transparent); }
    50% { box-shadow: 0 0 0 6px transparent; } }
  .rf { width: 36px; height: 36px; min-width: 36px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; cursor: pointer; color: var(--secondary-text-color); transition: background .18s; }
  .rf:hover { background: var(--secondary-background-color, rgba(127,127,127,.12)); color: var(--primary-text-color); }
  .rf.off { opacity: .4; pointer-events: none; }
  .rf ha-icon { --mdc-icon-size: 20px; }
  .spin { animation: rot 1s linear infinite; }
  @keyframes rot { to { transform: rotate(360deg); } }
  .summary { padding: 6px 0 10px; font-size: .9rem; line-height: 1.5; color: var(--primary-text-color); }
  .summary.wait { color: var(--secondary-text-color); font-style: italic; }
  .reco { display: flex; align-items: flex-start; gap: 10px; margin: 0 0 12px; padding: 10px 12px;
    border-radius: 12px; cursor: pointer; border-left: 3px solid var(--hz);
    background: color-mix(in srgb, var(--hz) 10%, transparent); transition: background .4s, border-color .4s; }
  .reco:hover { background: color-mix(in srgb, var(--hz) 16%, transparent); }
  .reco ha-icon { --mdc-icon-size: 18px; color: var(--hz); margin-top: 1px; }
  .cap { font-size: 11px; letter-spacing: .5px; text-transform: uppercase; color: var(--secondary-text-color); }
  .reco-t { font-size: .85rem; line-height: 1.45; color: var(--primary-text-color); margin-top: 2px; }
  .rows-h { display: flex; align-items: baseline; gap: 8px; margin: 2px 0 6px; }
  .pend { margin-left: auto; font-size: 11px; font-style: italic; color: var(--secondary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
  .rows { display: flex; flex-direction: column; gap: 6px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 14px; cursor: pointer;
    background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); transition: background .25s; }
  .row:hover { background: color-mix(in srgb, var(--primary-text-color) 10%, transparent); }
  .ic { width: 32px; height: 32px; min-width: 32px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; color: var(--secondary-text-color);
    background: color-mix(in srgb, var(--secondary-text-color) 10%, transparent); transition: color .4s, background .4s; }
  .ic ha-icon { --mdc-icon-size: 19px; }
  .nm { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .n { font-size: 13px; font-weight: 500; color: var(--primary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .lv { font-size: 11px; font-weight: 600; color: var(--secondary-text-color); transition: color .4s; }
  .segs { display: flex; gap: 4px; }
  .seg { width: 20px; height: 8px; border-radius: 4px; transition: background .4s, box-shadow .4s;
    background: var(--divider-color, rgba(127,127,127,.25)); }
  .foot { display: flex; align-items: center; gap: 10px; margin-top: auto; padding-top: 12px; cursor: pointer; }
  .cf-t { flex: 1; height: 6px; border-radius: 3px; overflow: hidden; background: var(--divider-color, rgba(127,127,127,.25)); }
  .cf-b { height: 100%; width: 0; border-radius: 3px; background: var(--primary-color, #03a9f4);
    transition: width .8s cubic-bezier(.4,0,.2,1); }
  .cf-v { font-size: 12px; font-weight: 600; color: var(--primary-text-color); }
  .empty { padding: 8px 0; color: var(--secondary-text-color); font-size: .9rem; }
</style>
<ha-card>
  <div class="head" id="head">
    <div class="shape"><ha-icon id="shield" icon="mdi:shield-check"></ha-icon></div>
    <div class="tt"><div class="title">${title}</div><div class="sub" id="sub">${esc(this._t("subtitle"))}</div></div>
    <div class="pill" id="pill"><span class="dot"></span><span id="pilltxt">--</span></div>
    <div class="rf" id="rf" title="${esc(this._t("analyze"))}"><ha-icon icon="mdi:refresh"></ha-icon></div>
  </div>
  <div class="empty" id="empty" hidden>${esc(this._t("no_entity"))}</div>
  <div class="summary" id="summary"></div>
  <div class="reco" id="reco" hidden>
    <ha-icon icon="mdi:lightbulb-on-outline"></ha-icon>
    <div><div class="cap">${esc(this._t("recommended"))}</div><div class="reco-t" id="recotxt"></div></div>
  </div>
  <div class="rows-h"><span class="cap">${esc(this._t("categories"))}</span>
    <span class="pend" id="pend" hidden title="${esc(this._t("pending_hint"))}">${esc(this._t("pending"))}</span></div>
  <div class="rows">${CATEGORIES.map((cat) => `
    <div class="row" data-k="${cat.key}">
      <div class="ic" id="ic-${cat.key}"><ha-icon icon="${cat.icon}"></ha-icon></div>
      <div class="nm"><span class="n">${esc(this._t(cat.key))}</span><span class="lv" id="lv-${cat.key}">--</span></div>
      <div class="segs">${[0, 1, 2, 3].map((i) => `<div class="seg" id="s-${cat.key}-${i}"></div>`).join("")}</div>
    </div>`).join("")}
  </div>
  <div class="foot" id="foot" title="${esc(this._t("confidence_hint"))}">
    <span class="cap">${esc(this._t("confidence"))}</span>
    <div class="cf-t"><div class="cf-b" id="conf"></div></div>
    <span class="cf-v" id="confval">--</span>
  </div>
</ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const e = () => this._entities();
    $("head").addEventListener("click", () => this._more(e().risk_level));
    $("reco").addEventListener("click", () => this._more(e().recommendation));
    $("pend").addEventListener("click", () => this._more(e().deescalation_pending));
    $("foot").addEventListener("click", () => this._more(e().confidence));
    this.shadowRoot.querySelectorAll(".row").forEach((row) =>
      row.addEventListener("click", () => this._more(e()[row.dataset.k]))
    );
    $("rf").addEventListener("click", (ev) => {
      ev.stopPropagation();
      const button = e().analyze_now;
      if (button) this._hass.callService("button", "press", { entity_id: button });
    });
  }

  _update() {
    if (!this._hass || !this._built) return;
    const c = this._config;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const ents = this._entities();
    const risk = this._st(ents.risk_level);
    $("empty").hidden = !!risk;

    let max = 0;
    let known = false;
    for (const cat of CATEGORIES) {
      const st = this._st(ents[cat.key]);
      const ok = st && !BAD.has(st.state);
      const lvl = ok ? clampLevel(st.state) : 0;
      known = known || ok;
      max = Math.max(max, lvl);
      const col = SEV_COLORS[lvl];
      for (let i = 0; i < 4; i++) {
        const seg = $(`s-${cat.key}-${i}`);
        const on = i < lvl;
        seg.style.background = on ? col : "";
        seg.style.boxShadow = on ? `0 0 5px ${col}` : "none";
      }
      const lv = $(`lv-${cat.key}`);
      lv.textContent = ok ? this._t("level_" + LEVELS[lvl]) : this._t("no_data");
      lv.style.color = lvl > 0 ? col : "";
      const ic = $(`ic-${cat.key}`);
      ic.style.color = lvl > 0 ? col : "";
      ic.style.background = lvl > 0 ? `color-mix(in srgb, ${col} 16%, transparent)` : "";
    }

    const color = !known ? "var(--disabled-text-color, #9e9e9e)" : max === 0 ? OK_COLOR : SEV_COLORS[max];
    this.shadowRoot.querySelector("ha-card").style.setProperty("--hz", color);
    $("shield").setAttribute("icon", max === 0 ? "mdi:shield-check" : max >= 4 ? "mdi:alarm-light" : "mdi:shield-alert");
    const pill = $("pill");
    pill.classList.toggle("alert", max >= 3);
    $("pilltxt").textContent = !known ? "--" : max === 0 ? this._t("all_clear") : this._t("level_" + LEVELS[max]);

    // Summary and recommendation
    const sum = this._st(ents.summary);
    const sumTxt = sum && !BAD.has(sum.state) ? sum.state : "";
    const summary = $("summary");
    summary.hidden = !c.show_summary;
    summary.textContent = sumTxt || this._t("waiting");
    summary.classList.toggle("wait", !sumTxt);
    const reco = this._st(ents.recommendation);
    const showReco = c.show_recommendation && reco && !BAD.has(reco.state) && reco.attributes.action_required !== false;
    $("reco").hidden = !showReco;
    $("recotxt").textContent = showReco ? reco.state : "";

    const pend = this._st(ents.deescalation_pending);
    $("pend").hidden = !(pend && pend.state === "on" && max > 0);

    // Header subtitle: running > paused > failed > stale > updated
    const running = this._st(ents.analyzing);
    const isRunning = running && running.state === "on";
    const monitoring = this._st(ents.monitoring);
    const problem = this._st(ents.problem);
    const last = this._st(ents.last_analysis);
    const lastTs = last && !BAD.has(last.state) ? Date.parse(last.state) : NaN;
    const age = isNaN(lastTs) ? null : Math.max(0, (Date.now() - lastTs) / 1000);
    const sub = $("sub");
    let warn = false;
    if (isRunning) sub.textContent = this._t("running");
    else if (monitoring && monitoring.state === "off") sub.textContent = this._t("paused");
    else if (problem && problem.state === "on") {
      warn = true;
      sub.textContent = problem.attributes.last_error || age === null
        ? this._t("failed")
        : this._t("stale", { dur: this._dur(age) });
    } else sub.textContent = age === null ? this._t("subtitle") : this._t("updated", { ago: this._ago(age) });
    sub.classList.toggle("warn", warn);

    const rf = $("rf");
    rf.hidden = !(c.show_refresh && ents.analyze_now);
    rf.classList.toggle("off", !!isRunning);
    rf.querySelector("ha-icon").classList.toggle("spin", !!isRunning);

    // Confidence
    const conf = this._st(ents.confidence);
    const cv = conf && !BAD.has(conf.state) ? parseFloat(conf.state) : NaN;
    $("foot").hidden = !c.show_confidence || isNaN(cv);
    if (!isNaN(cv)) {
      $("conf").style.width = Math.max(0, Math.min(100, cv * 10)) + "%";
      $("confval").textContent = Math.round(cv) + "/10";
    }
  }
}

class HazardAnalysisCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = Object.assign({}, config);
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _schema() {
    return [
      { name: "entity", required: true, selector: { entity: { integration: INTEGRATION, domain: "sensor" } } },
      { name: "name", selector: { text: {} } },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "show_summary", selector: { boolean: {} } },
          { name: "show_recommendation", selector: { boolean: {} } },
          { name: "show_confidence", selector: { boolean: {} } },
          { name: "show_refresh", selector: { boolean: {} } }
        ]
      }
    ];
  }

  async _update() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      await ensureHaForm();
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => t(this._hass, "e_" + s.name);
      this._form.addEventListener("value-changed", (ev) => {
        const value = Object.assign({}, ev.detail.value);
        for (const k of Object.keys(value)) if (value[k] === "" || value[k] == null) delete value[k];
        this._config = value;
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: Object.assign({ type: "custom:" + CARD_TAG }, value) }, bubbles: true, composed: true
        }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = Object.assign(
      { show_summary: true, show_recommendation: true, show_confidence: true, show_refresh: true },
      this._config
    );
    this._form.schema = this._schema();
  }
}

if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, HazardAnalysisCardEditor);
if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, HazardAnalysisCard);
  window.customCards = window.customCards || [];
  const lang = langOf(document.querySelector("home-assistant") && document.querySelector("home-assistant").hass);
  const table = STRINGS[lang] || STRINGS.en;
  window.customCards.push({
    type: CARD_TAG,
    name: table.card_name,
    description: table.card_description,
    preview: true,
    documentationURL: "https://github.com/artech-lab/ha-hazard-analysis"
  });
  console.info(`%c HAZARD-ANALYSIS-CARD %c ${CARD_VERSION} `, "color:#fff;background:#e53935;font-weight:700", "color:#e53935;background:#fff");
}
