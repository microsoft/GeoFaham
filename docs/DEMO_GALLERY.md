# Demo gallery

Four edited recordings show raster, vector, and imagery workflows. Requests
are shortened from the recorded prompts. Captions identify the steps; cuts skip
waiting and processing time, so GIF duration is not execution time.

## Burn-severity raster

> Map burn severity for the January 2025 Southern California wildfires using pre- and post-fire satellite imagery.

GeoFaham generates a burn-severity raster from pre- and post-fire imagery. The
recording shows the selected AOI, colored output, burn-scar inspection, and legend.

<details>
<summary>Watch the burn-severity workflow (12 seconds)</summary>

![Question and selected area followed by the Southern California burn-severity raster and burn-scar inspection](figures/gifs/geofaham-burn-severity-demo.gif)

</details>

## Kenya flood analysis

> Which schools intersect the mapped flood extent from the 2024 Kenya floods?

The workflow retrieves the flood layer, finds school locations, and intersects
the layers to identify potentially affected schools. The map progresses from
flood extent to school locations and the resulting intersection layer.

<details>
<summary>Watch the flood-and-schools workflow (12 seconds)</summary>

![Kenya flood extent, retrieved school locations, and schools intersecting the flood layer, with question and step captions](figures/gifs/geofaham-flood-map-demo.gif)

</details>

## St. Louis building damage

> Compare 2025 tornado building damage in Central West End and Academy / Sherman Park, St. Louis.

GeoFaham combines neighborhood boundaries with existing building-damage
assessments. The map shows building-level damage and a shared legend alongside
the conversational comparison.

<details>
<summary>Watch the neighborhood damage comparison (10 seconds)</summary>

![St. Louis neighborhood boundaries, tornado building-damage records, legend, and comparison summary, with a readable request banner](figures/gifs/geofaham-building-damage-demo.gif)

</details>

## Satellite imagery timeline

> Show shortwave-infrared imagery for this area of Maui from August 1 to August 20, 2023.

GeoFaham retrieves shortwave-infrared imagery for the selected AOI. The timeline
control switches between available acquisition dates.

<details>
<summary>Watch the imagery-and-timeline workflow (12 seconds)</summary>

![Maui area selection, retrieved shortwave-infrared imagery, and temporal selection controls, with question and step captions](figures/gifs/geofaham-imagery-timeline-demo.gif)

</details>

See the [web interface documentation](UI_DOCUMENTATION.md) for map controls,
or return to the [project README](../README.md).
