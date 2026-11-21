# Area Occupancy Dashboard

Area Occupancy includes a dashboard strategy that builds a Lovelace dashboard
from the areas and entities configured in your Home Assistant instance.

## Add the dashboard

After installing or updating the integration, open **Settings → Dashboards →
Add dashboard**. Choose **Area Occupancy** under Community dashboards. The
integration registers the strategy automatically when Home Assistant starts.

Alternatively, create a dashboard in YAML mode with:

```yaml
strategy:
  type: custom:area-occupancy
```

The dashboard is generated when it is created. If you add or remove areas
later, recreate the dashboard from the strategy to refresh its views.

## Views

- **Status** is the first view, grouped by Home Assistant floor. Within a floor,
  connected areas are placed near each other using configured Area Occupancy
  adjacency; areas without connections fall back to name order. Each card shows its current activity,
  occupancy probability, color-coded reason, timer, and input counts. **Primary**
  counts active non-environmental inputs, **Decaying** counts fading inputs,
  and **Environmental** counts active sensor-domain inputs.
- **Forecast** shows learned weekly occupancy patterns for configured areas.
- **Thresholds** collects each area's occupancy threshold.
- **Metadata** shows whole-home and floor rollups plus per-area probability,
  priors, activity, evidence, and any enabled diagnostics.
- **History** includes whole-home and floor rollup probabilities, area
  probabilities, occupancy status, detected activity, and per-area thresholds.
- **Diagnostics** includes the corresponding entities that are enabled in Home
  Assistant.
- Each configured area gets a detail view with occupancy, probability,
  threshold, detected activity, sensors assigned to that Home Assistant area,
  enabled diagnostics, history, and a weekly forecast.

Area detail views use [Auto-Entities](https://github.com/thomasloven/lovelace-auto-entities)
to discover the sensors assigned to each Home Assistant area. The Status view's
live timers use [Button Card](https://github.com/custom-cards/button-card).
Install those cards for the dynamic sensor lists and live timers. The
integration's time-priors heatmap is bundled and loaded automatically.
Standard Home Assistant cards provide the rest of the dashboard.

!!! tip "Show more calculation details"
    Diagnostic entities are disabled by default for new areas. Enable the ones
    you want to see under **Settings → Devices & Services → Area Occupancy
    Detection → Devices → select an area → disabled diagnostic entity → Settings
    → Enable**. The dashboard will then include those entities in its
    Diagnostics view. See [Entities](entities.md#diagnostic-entities) for
    the available diagnostics and their attributes.

Entities disabled in the entity registry are not added to diagnostic sections.
The dashboard only displays entities that are enabled and available to the
current Home Assistant user.
