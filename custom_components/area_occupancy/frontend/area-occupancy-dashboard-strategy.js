/* Area Occupancy dashboard strategy. Entity IDs are resolved from HA registries,
 * so entity renames and different room/floor names do not require YAML edits. */
const STRATEGY_TYPE = "area-occupancy";
const DOMAIN = "area_occupancy";

const slug = (value) => String(value || "area").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "area";
const title = (value) => String(value || "").replaceAll("_", " ");

function identifiers(device) {
  return (device.identifiers || []).map((item) => Array.isArray(item) ? item[1] : item.identifier).filter(Boolean);
}

function entitiesForDevice(device, registry) {
  return registry.filter((entity) => entity.platform === DOMAIN && entity.device_id === device.id);
}

function findEntity(entities, suffix, includeDisabled = false) {
  return entities.find((entity) => (includeDisabled || !entity.disabled_by) && entity.unique_id.endsWith(`_${suffix}`))?.entity_id;
}

function entityCard(entity, name) {
  return entity ? { type: "tile", entity, name } : undefined;
}

function sections(cards, columns = 4) {
  const live = cards.filter(Boolean);
  return live.length ? [{ type: "grid", cards: live, column_span: Math.min(columns, 4) }] : [];
}

function orderByAdjacency(items) {
  const byId = new Map(items.map((item) => [item.area.area_id, item]));
  const remaining = new Set(byId.keys());
  const ordered = [];
  const neighbours = (id, candidates) => (byId.get(id)?.adjacentAreas || [])
    .filter((neighbour) => candidates.has(neighbour));
  const nameFor = (id) => byId.get(id)?.area.name || id;

  while (remaining.size) {
    const starts = [...remaining].sort((left, right) =>
      neighbours(right, remaining).length - neighbours(left, remaining).length ||
      nameFor(left).localeCompare(nameFor(right)));
    const queue = [starts[0]];
    remaining.delete(starts[0]);
    while (queue.length) {
      const current = queue.shift();
      ordered.push(byId.get(current));
      const connected = neighbours(current, remaining).sort((left, right) =>
        neighbours(right, remaining).length - neighbours(left, remaining).length ||
        nameFor(left).localeCompare(nameFor(right)));
      for (const neighbour of connected) {
        remaining.delete(neighbour);
        queue.push(neighbour);
      }
    }
  }
  return ordered;
}

function statusTimerCard(area, entities) {
  const status = findEntity(entities, "occupancy_status");
  const probability = findEntity(entities, "occupancy_probability");
  const threshold = findEntity(entities, "occupancy_threshold");
  const activity = findEntity(entities, "detected_activity");
  if (!status || !probability || !threshold) return undefined;

  const statusId = JSON.stringify(status);
  const thresholdId = JSON.stringify(threshold);
  const activityId = JSON.stringify(activity || "");
  const reading = `[[[
    const occupied = states[${statusId}]?.state === "on";
    const threshold = parseFloat(states[${thresholdId}]?.state || 50);
    const probability = parseFloat(entity?.state || 0);
    const activityState = states[${activityId}]?.state;
    const activity = activityState ? activityState.replaceAll("_", " ") : "Activity unavailable";
    const active = entity?.attributes?.active_entities || [];
    const halfLives = entity?.attributes?.decaying_half_lives || {};
    const decaying = (entity?.attributes?.decaying_entities || []).map((item) => typeof item === "string" ? { entity_id: item, decay_factor: 0, half_life: halfLives[item] } : { ...item, half_life: halfLives[item.entity_id] });
    const decayingIds = decaying.map((item) => typeof item === "string" ? item : item.entity_id);
    const live = active.filter((id) => !decayingIds.includes(id));
    const primary = live.filter((id) => !id.startsWith("sensor."));
    const environmental = live.filter((id) => id.startsWith("sensor."));
    const counts = "Primary " + primary.length + " · Decaying " + decaying.length + " · Environmental " + environmental.length;
    const prior = parseFloat(entity?.attributes?.prior_value || 0) * 100;
    const cleanup = () => {
      this._cdEnd = null;
      if (this._cdTimer) { clearInterval(this._cdTimer); this._cdTimer = null; }
    };
    if (!occupied) {
      cleanup();
      return "<span style='opacity:.65'>⚪ " + activity + " · " + counts + " · " + Math.round(probability) + "% / " + Math.round(threshold) + "%</span>";
    }
    if (primary.length) {
      cleanup();
      return "<span style='color:#4caf50'>🟢 " + activity + " · " + counts + " · " + Math.round(probability) + "% / " + Math.round(threshold) + "%</span>";
    }
    if (prior >= threshold) {
      cleanup();
      return "<span style='color:#ffc107'>🟡 " + activity + " · Learned prior · " + counts + " · " + Math.round(probability) + "% / " + Math.round(threshold) + "%</span>";
    }
    if (decaying.length) {
      const dominant = decaying.reduce((best, item) => parseFloat(item.decay_factor || 0) > parseFloat(best.decay_factor || 0) ? item : best);
      const maxDecay = Math.max(0.05, parseFloat(dominant.decay_factor || 0));
      const halfLife = parseFloat(dominant.half_life || 0);
      const p = Math.min(0.99, Math.max(0.01, probability / 100));
      const t = Math.min(0.99, Math.max(0.01, threshold / 100));
      const p0 = Math.min(0.99, Math.max(0.01, prior / 100));
      const lp = Math.log(p / (1 - p));
      const lt = Math.log(t / (1 - t));
      const l0 = Math.log(p0 / (1 - p0));
      const ratio = lp > l0 + 0.001 ? Math.max(0, Math.min(1, (lt - l0) / (lp - l0))) : 0;
      const crossing = Math.max(maxDecay * ratio, 0.05);
      const seconds = halfLife > 0 ? Math.max(0, Math.round(halfLife * Math.log(maxDecay / crossing) / Math.LN2)) : 0;
      const base = entity?.last_updated ? new Date(entity.last_updated).getTime() : Date.now();
      this._cdEnd = base + seconds * 1000;
      const remaining = Math.max(0, Math.round((this._cdEnd - Date.now()) / 1000));
      const time = remaining >= 60 ? "~" + Math.floor(remaining / 60) + "m " + (remaining % 60) + "s" : (remaining ? "~" + remaining + "s" : "< 10s");
      if (!this._cdTimer) {
        this._cdTimer = setInterval(() => {
          if (!this.isConnected || !this._cdEnd) { clearInterval(this._cdTimer); this._cdTimer = null; return; }
          const value = Math.max(0, Math.round((this._cdEnd - Date.now()) / 1000));
          const node = this.shadowRoot?.querySelector(".cd-txt");
          if (node) node.textContent = value >= 60 ? "~" + Math.floor(value / 60) + "m " + (value % 60) + "s" : (value ? "~" + value + "s" : "< 10s");
        }, 1000);
      }
      return "<span style='color:#ff9800'>🟠 " + activity + " · ⏳ <span class='cd-txt'>" + time + "</span> · " + counts + " · " + Math.round(probability) + "% / " + Math.round(threshold) + "%</span>";
    }
    cleanup();
    const reason = environmental.length ? "Environmental support" : "Prior support";
    return "<span style='color:#ffc107'>🟡 " + activity + " · " + reason + " · " + counts + " · " + Math.round(probability) + "% / " + Math.round(threshold) + "%</span>";
  ]]]`;
  const bar = `[[[
    const occupied = states[${statusId}]?.state === "on";
    const threshold = parseFloat(states[${thresholdId}]?.state || 50);
    const probability = parseFloat(entity?.state || 0);
    const active = entity?.attributes?.active_entities || [];
    const halfLives = entity?.attributes?.decaying_half_lives || {};
    const decaying = (entity?.attributes?.decaying_entities || []).map((item) => typeof item === "string" ? { entity_id: item, decay_factor: 0, half_life: halfLives[item] } : { ...item, half_life: halfLives[item.entity_id] });
    const ids = decaying.map((item) => typeof item === "string" ? item : item.entity_id);
    const livePrimary = active.some((id) => !ids.includes(id) && !id.startsWith("sensor."));
    const prior = parseFloat(entity?.attributes?.prior_value || 0) * 100;
    const base = "height:6px;border-radius:3px;overflow:hidden;width:100%;";
    if (!occupied) {
      const width = threshold > 0 ? Math.min(100, Math.max(0, probability / threshold * 100)) : 0;
      return "<div style='" + base + "background:rgba(128,128,128,.18)'><div style='height:100%;background:#9e9e9e;width:" + width + "%'></div></div>";
    }
    if (livePrimary) return "<div style='" + base + "background:#4caf50'></div>";
    if (prior >= threshold) return "<div style='" + base + "background:#ffc107'></div>";
    if (decaying.length) {
      const maxDecay = Math.max(...decaying.map((item) => parseFloat(item.decay_factor || 0)));
      const width = Math.min(100, Math.max(0, maxDecay * 100));
      return "<div style='" + base + "background:rgba(255,152,0,.2)'><div style='height:100%;background:#ff9800;width:" + width + "%'></div></div>";
    }
    return "<div style='" + base + "background:#ffc107'></div>";
  ]]]`;

  return {
    type: "custom:button-card",
    entity: probability,
    triggers_update: [status, probability, threshold, activity].filter(Boolean),
    name: area.name,
    icon: "mdi:home-account",
    tap_action: { action: "more-info" },
    custom_fields: { status: reading, bar },
    styles: {
      card: [{ "border-radius": "16px" }, { padding: "10px 14px" }],
      grid: [{ "grid-template-areas": "'i n' 'i status' 'bar bar'" }, { "grid-template-columns": "32px 1fr" }, { "grid-template-rows": "auto auto 6px" }, { "row-gap": "6px" }],
      icon: [{ color: "var(--primary-color)" }, { width: "22px" }],
      name: [{ "justify-self": "start" }, { "font-weight": "600" }],
      custom_fields: { status: [{ "grid-area": "status" }, { "justify-self": "start" }, { "font-size": "12px" }], bar: [{ "grid-area": "bar" }, { width: "100%" }] },
    },
  };
}

function areaMetadataCard(area, entities) {
  const status = findEntity(entities, "occupancy_status");
  const probability = findEntity(entities, "occupancy_probability");
  const threshold = findEntity(entities, "occupancy_threshold");
  const activity = findEntity(entities, "detected_activity");
  const evidence = findEntity(entities, "evidence", true);
  if (!probability) return undefined;
  const st = status ? `{% set st = '${status}' %}` : "{% set st = none %}";
  const th = threshold ? `{% set th = '${threshold}' %}` : "{% set th = none %}";
  const ac = activity ? `{% set ac = '${activity}' %}` : "{% set ac = none %}";
  const ev = evidence ? `{% set ev = '${evidence}' %}` : "{% set ev = none %}";
  const statusRow = status ? "| **Status** | {{ state_translated(st) }} · {{ relative_time(states[st].last_changed) ~ ' ago' if states[st] is defined else 'N/A' }} |" : "| **Status** | Not enabled |";
  const thresholdRow = threshold ? "| **Probability / Threshold** | {{ states(pr) }}% / {{ states(th) }}% |" : "| **Probability / Threshold** | {{ states(pr) }}% / threshold entity unavailable |";
  const activityRow = activity ? "| **Detected activity** | {{ state_translated(ac) }} · {{ state_attr(ac, 'confidence')|float(0)|round(1) }}% confidence |" : "| **Detected activity** | Not enabled |";
  const evidenceDetails = evidence ? `
**Sensor evidence**
{% set details = state_attr(ev, 'details') or [] %}
{% if details|count %}
| Sensor | State | Evidence | Decay | Health |
| :--- | :--- | :--- | ---: | :--- |
{% for item in details %}
| {{ item.name or item.id }} | {{ states(item.id) }} | {{ 'Active' if item.evidence else 'Inactive' }} | {{ (item.decay_factor*100)|round(0) if item.decaying and item.decay_factor is number else '—' }}% | {{ item.health_status or '—' }} |
{% endfor %}
{% else %}No sensor detail is available yet.{% endif %}` : "\nEnable the area's **Evidence** diagnostic entity to see its configured sensor details here.";
  return {
    type: "markdown",
    content: `${st}{% set pr = '${probability}' %}${th}${ac}${ev}
| Metric | Value |
| :--- | :--- |
| **Area** | ${area.name} |
${statusRow}
${thresholdRow}
${activityRow}
| **Prior (combined / time / global)** | {{ (state_attr(pr, 'prior_value')|float(0)*100)|round(1) }}% / {{ (state_attr(pr, 'time_prior')|float(0)*100)|round(1) }}% / {{ (state_attr(pr, 'global_prior')|float(0)*100)|round(1) }}% |
| **Minimum prior floor** | {{ state_attr(pr, 'min_prior_floor_applied') or 'None' }} |
| **Active evidence** | {{ (state_attr(pr, 'active_entities') or [])|count }} |
| **Decaying evidence** | {{ (state_attr(pr, 'decaying_entities') or [])|count }} |

**Why occupancy is held**
{% set active = state_attr(pr, 'active_entities') or [] %}
{% set decaying = state_attr(pr, 'decaying_entities') or [] %}
{% set decaying_ids = decaying|map(attribute='entity_id')|list %}
{% set live = active|reject('in', decaying_ids)|list %}
{% set primary = live|reject('match', '^sensor\\.')|list %}
{% set environmental = live|select('match', '^sensor\\.')|list %}
{% if st and is_state(st, 'on') and primary|count %}🟢 **Live primary evidence** ({{ primary|count }})
{% elif st and is_state(st, 'on') and decaying|count %}🟠 **Decaying evidence** ({{ decaying|count }}){% if environmental|count %} + {{ environmental|count }} environmental{% endif %}
{% elif st and is_state(st, 'on') and environmental|count %}🟡 **Environmental support** ({{ environmental|count }})
{% elif st and is_state(st, 'on') %}🟡 **Learned prior at or above threshold**
{% else %}⚪ **Not occupied**{% endif %}

**Active primary sensors:** {% if primary|count %}{% for eid in primary %}{{ state_attr(eid, 'friendly_name') or eid }}{% if not loop.last %}, {% endif %}{% endfor %}{% else %}None{% endif %}

**Decaying sensors:** {% if decaying|count %}{% for item in decaying %}{{ state_attr(item.entity_id, 'friendly_name') or item.entity_id }} ({{ (item.decay_factor*100)|round(0) }}%){% if not loop.last %}, {% endif %}{% endfor %}{% else %}None{% endif %}

**Environmental sensors:** {% if environmental|count %}{% for eid in environmental %}{{ state_attr(eid, 'friendly_name') or eid }}{% if not loop.last %}, {% endif %}{% endfor %}{% else %}None{% endif %}${evidenceDetails}`,
  };
}

function areaView(area, entities) {
  const status = findEntity(entities, "occupancy_status");
  const probability = findEntity(entities, "occupancy_probability");
  const threshold = findEntity(entities, "occupancy_threshold");
  const activity = findEntity(entities, "detected_activity");
  const cards = [
    status ? { type: "tile", entity: status, name: "Occupancy", state_content: ["state", "last_changed"] } : undefined,
    probability ? { type: "tile", entity: probability, name: "Probability", features: [{ type: "trend-graph", hours_to_show: 6 }], features_position: "bottom" } : undefined,
    threshold ? { type: "tile", entity: threshold, name: "Threshold", features: [{ type: "numeric-input", style: "slider" }], features_position: "bottom" } : undefined,
    entityCard(activity, "Detected activity"),
  ];
  const controls = sections(cards);
  const diagnostics = entities
    .filter((entity) => entity.entity_category === "diagnostic" && !entity.disabled_by)
    .map((entity) => entity.entity_id);
  const inputs = area.area_id
    ? { include: [{ area: area.area_id }], exclude: [{ integration: DOMAIN }] }
    : undefined;
  const more = [];
  more.push(areaMetadataCard(area, entities));
  if (inputs) more.push({ type: "custom:auto-entities", card: { type: "entities", title: "Area sensors" }, filter: { ...inputs, include: inputs.include.map((item) => ({ ...item, options: {} })) }, sort: { method: "name" } });
  if (diagnostics.length) more.push({ type: "entities", title: "Diagnostics", entities: diagnostics });
  if (probability || threshold || status || activity) {
    const historyEntities = [probability, threshold, status, activity].filter(Boolean);
    more.push({ type: "history-graph", title: "Last 24 hours", hours_to_show: 24, entities: historyEntities });
  }
  more.push({ type: "custom:area-occupancy-time-priors-card", title: `${area.name} weekly forecast`, area_id: area.area_id || identifiers(area.device)[0] });
  return {
    title: area.name,
    path: `area-${slug(area.name)}-${slug(area.area_id || area.id)}`,
    icon: area.icon || "mdi:home-outline",
    type: "sections",
    max_columns: 3,
    sections: [...controls, ...sections(more, 3)],
  };
}

class AreaOccupancyDashboardStrategy extends HTMLElement {
  static getCreateSuggestions() {
    return { title: "Area Occupancy", icon: "mdi:home-account" };
  }

  static async generate(config, hass) {
    const [areas, floors, devices, registry] = await Promise.all([
      hass.callWS({ type: "config/area_registry/list" }),
      hass.callWS({ type: "config/floor_registry/list" }),
      hass.callWS({ type: "config/device_registry/list" }),
      hass.callWS({ type: "config/entity_registry/list" }),
    ]);
    const integrationDevices = devices.filter((device) => identifiers(device).length &&
      (device.identifiers || []).some((item) => (Array.isArray(item) ? item[0] : item.domain) === DOMAIN));
    const aggregateDevices = integrationDevices.filter((device) => identifiers(device)
      .some((id) => id === "all_areas" || id.startsWith("floor_")));
    const areaDevices = integrationDevices.filter((device) => !identifiers(device).some((id) => id === "all_areas" || id.startsWith("floor_")));
    const configured = areaDevices.map((device) => {
      const id = identifiers(device)[0];
      const area = areas.find((candidate) => candidate.area_id === id) ||
        areas.find((candidate) => candidate.name === device.name);
      const entities = entitiesForDevice(device, registry);
      const probability = findEntity(entities, "occupancy_probability");
      const adjacentAreas = probability
        ? hass.states[probability]?.attributes?.adjacent_areas || []
        : [];
      return { id, device, area: area || { area_id: id, name: device.name || title(id) }, entities, adjacentAreas };
    }).filter((item) => item.entities.length);

    const groups = new Map();
    for (const item of configured) {
      const floor = areas.find((candidate) => candidate.area_id === item.area.area_id)?.floor_id;
      const key = floor ? `floor:${floor}` : "areas";
      const label = floor ? (floors.find((candidate) => candidate.floor_id === floor)?.name || title(floor)) : "Areas";
      if (!groups.has(key)) groups.set(key, { label, floorId: floor || null, areas: [] });
      groups.get(key).areas.push(item);
    }
    const forecastAreas = configured.map(({ area, id }) => ({ area, id }));
    const thresholdSections = [...groups.values()].map((group) => {
      const cards = group.areas.map(({ area, entities }) =>
        entityCard(findEntity(entities, "occupancy_threshold"), area.name)).filter(Boolean);
      return cards.length ? { type: "grid", cards: [
        { type: "heading", heading: group.label, heading_style: "title" },
        ...cards,
      ] } : undefined;
    }).filter(Boolean);
    const histories = configured.map(({ area, entities }) => {
      const probability = findEntity(entities, "occupancy_probability");
      const status = findEntity(entities, "occupancy_status");
      const threshold = findEntity(entities, "occupancy_threshold");
      const activity = findEntity(entities, "detected_activity");
      return probability || status ? { type: "history-graph", title: area.name, hours_to_show: 24, entities: [probability, threshold, status, activity].filter(Boolean) } : undefined;
    }).filter(Boolean);
    const aggregateProbabilities = aggregateDevices.flatMap((device) => {
      const probability = findEntity(entitiesForDevice(device, registry), "occupancy_probability");
      return probability ? [{ entity: probability, name: device.name }] : [];
    });
    const floorHistories = [...groups.values()].map((group) => {
      const members = group.areas.flatMap(({ area, entities }) => {
        const probability = findEntity(entities, "occupancy_probability");
        return probability ? [{ entity: probability, name: area.name }] : [];
      });
      return members.length ? { type: "history-graph", title: `${group.label} area probabilities (24h)`, hours_to_show: 24, entities: members } : undefined;
    }).filter(Boolean);
    const statusHistory = configured.flatMap(({ area, entities }) => {
      const status = findEntity(entities, "occupancy_status");
      return status ? [{ entity: status, name: area.name }] : [];
    });
    const activityHistory = configured.flatMap(({ area, entities }) => {
      const activity = findEntity(entities, "detected_activity");
      return activity ? [{ entity: activity, name: area.name }] : [];
    });
    const statusFloorSections = [...groups.values()].sort((left, right) => {
      const leftLevel = floors.find((floor) => floor.floor_id === left.floorId)?.level;
      const rightLevel = floors.find((floor) => floor.floor_id === right.floorId)?.level;
      if (leftLevel != null && rightLevel != null && leftLevel !== rightLevel) return leftLevel - rightLevel;
      if (left.floorId && !right.floorId) return -1;
      if (!left.floorId && right.floorId) return 1;
      return left.label.localeCompare(right.label);
    }).map((group) => {
      const cards = orderByAdjacency(group.areas)
        .map(({ area, entities }) => statusTimerCard(area, entities))
        .filter(Boolean);
      return cards.length ? {
        type: "grid",
        column_span: 3,
        cards: [
          { type: "heading", heading: group.label, heading_style: "title", icon: "mdi:floor-plan" },
          ...cards,
        ],
      } : undefined;
    }).filter(Boolean);
    const statusSection = statusFloorSections.length ? [
      {
        type: "grid",
        column_span: 3,
        cards: [
          { type: "heading", heading: "Area Status & Timers", heading_style: "title", icon: "mdi:timer-outline" },
          { type: "markdown", content: "Each card shows the area's current detected activity and occupancy probability. 🟢 live primary evidence · 🟠 decaying evidence with an estimated countdown · 🟡 environmental or learned-prior support · ⚪ below threshold. Counts: **Primary** = active non-environmental inputs; **Decaying** = fading inputs; **Environmental** = active sensor-domain inputs. Orange countdowns are estimates; live evidence or a learned prior above threshold can keep an area occupied longer." },
        ],
      },
      ...statusFloorSections,
    ] : [];
    const aggregateMetadataSections = aggregateDevices.map((device) => {
      const entities = entitiesForDevice(device, registry)
        .filter((entity) => !entity.disabled_by)
        .map((entity) => entity.entity_id);
      return entities.length ? { type: "grid", cards: [
        { type: "heading", heading: device.name, heading_style: "title" },
        { type: "entities", entities },
      ] } : undefined;
    }).filter(Boolean);
    const metadataSections = [...aggregateMetadataSections, ...configured.map(({ area, entities }) => ({
      type: "grid",
      cards: [
        { type: "heading", heading: area.name, heading_style: "title" },
        ...[
          entityCard(findEntity(entities, "occupancy_status"), "Occupancy"),
          entityCard(findEntity(entities, "occupancy_probability"), "Probability"),
          entityCard(findEntity(entities, "detected_activity"), "Detected activity"),
          entityCard(findEntity(entities, "occupancy_threshold"), "Threshold"),
          areaMetadataCard(area, entities),
        ].filter(Boolean),
      ],
    }))];
    const historySections = sections([
      aggregateProbabilities.length ? { type: "history-graph", title: "Whole home & floor probabilities (24h)", hours_to_show: 24, entities: aggregateProbabilities } : undefined,
      ...floorHistories,
      statusHistory.length ? { type: "history-graph", title: "Occupancy status by area (24h)", hours_to_show: 24, entities: statusHistory } : undefined,
      activityHistory.length ? { type: "history-graph", title: "Detected activity by area (24h)", hours_to_show: 24, entities: activityHistory } : undefined,
      ...histories,
    ], 3);
    const views = [
      { title: "Status", path: "status", icon: "mdi:home-account", type: "sections", max_columns: 3, sections: statusSection },
      { title: "Forecast", path: "forecast", icon: "mdi:chart-box", type: "sections", max_columns: 2, sections: sections([{ type: "custom:area-occupancy-time-priors-card", title: "Weekly occupancy forecast" }], 2) },
      { title: "Thresholds", path: "thresholds", icon: "mdi:tune-variant", type: "sections", max_columns: 4, sections: thresholdSections },
      { title: "History", path: "history", icon: "mdi:chart-line", type: "sections", max_columns: 3, sections: historySections },
      { title: "Metadata", path: "metadata", icon: "mdi:database-eye", type: "sections", max_columns: 4, sections: metadataSections },
      { title: "Diagnostics", path: "diagnostics", icon: "mdi:clipboard-pulse", type: "sections", max_columns: 3, sections: sections([{
        type: "custom:auto-entities",
        card: { type: "entities", title: "Enabled diagnostic entities" },
        show_empty: false,
        filter: { include: [{ integration: DOMAIN, entity_category: "diagnostic" }] },
        sort: { method: "name" },
      }], 3) },
      ...forecastAreas.map(({ area, id }) => {
        const device = areaDevices.find((candidate) => identifiers(candidate).includes(id));
        return areaView({ ...area, device, id }, entitiesForDevice(device, registry));
      }),
    ];
    return { title: config.title || "Area Occupancy", views };
  }
}

customElements.define(`ll-strategy-dashboard-${STRATEGY_TYPE}`, AreaOccupancyDashboardStrategy);
window.customStrategies = window.customStrategies || [];
if (!window.customStrategies.some((item) => item.type === STRATEGY_TYPE && item.strategyType === "dashboard")) {
  window.customStrategies.push({
    type: STRATEGY_TYPE,
    strategyType: "dashboard",
    name: "Area Occupancy",
    description: "A live dashboard generated from your configured areas and Area Occupancy entities.",
    documentationURL: "https://hankanman.github.io/Area-Occupancy-Detection/",
  });
}
