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

The dashboard regenerates automatically when loaded or reloaded if you add or remove
areas. Recreating it is only needed if you previously clicked **Take control**.

## Views

- **Status** is grouped by Home Assistant floor. Connected areas appear near each other using configured adjacency. Each area card shows activity, probability, threshold, and evidence counts; tapping it opens that area as a subview.
- **Forecast** fills the available view width. Its comfort threshold is the average of enabled area thresholds (50% when no threshold values are available).
- **Info** appears only when issues are detected (such as disabled diagnostic entities, disabled or unavailable core entities, sensor health anomalies, or missing areas) and links to the affected devices so you can fix them.
- Each configured area has a subview with occupancy controls, a **Sensors & Decay** list, recent history, and a weekly forecast.

Area detail views use [Auto-Entities](https://github.com/thomasloven/lovelace-auto-entities)
to populate each room's active and decaying sensors from its **Evidence**
sensor's `details` attribute. [Button Card](https://github.com/custom-cards/button-card)
renders the floor, area, and sensor cards. Install those cards for the dynamic
sensor lists and interactive cards. The integration's time-priors heatmap is
bundled and loaded automatically. Standard Home Assistant cards provide the rest
of the dashboard.
