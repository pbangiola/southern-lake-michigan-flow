# Southern Lake Michigan Flow Atlas

An open-source project to visualize streams and rivers of northeastern Illinois, northwestern Indiana, and southwestern Michigan using discharge-weighted cartography.

## Goals

- One reproducible hydrography and discharge data pipeline
- Interactive web map with stream information and paddling access points
- Print-ready SVG and PDF maps from the same processed data
- Clear provenance, uncertainty, and distinction between observed and modeled flow

## Inspiration and credit

This independent project is inspired by [Flow — Bellingham streamflow cartography](https://flows.bellingham.dev/about.html). Credit belongs to the original project's creator for the inspiration and visual approach. We are not affiliated with the original project. Before copying any code, artwork, or other protected materials, we will verify their licenses and comply with their terms.

## Initial geography

Start with the southern Lake Michigan region, especially the Chicago–Calumet waterways, then expand to Trail Creek, Galien River, St. Joseph River, and nearby watersheds. Artificial diversions and drainage boundaries require special attention.

## Planned data pipeline

1. Retrieve hydrography, discharge, and elevation datasets from authoritative sources (USGS NHDPlus/3DHP, Water Data APIs, 3DEP).
2. Normalize stream identifiers, geometries, and units; record source and date.
3. Join observed and modeled discharge, retaining source/uncertainty flags.
4. Generate web-friendly GeoJSON/vector tiles and print-ready SVG/PDF.
5. Validate representative streams and engineered flow reversals before scaling up.

## Paddling access layer

A separate dataset will record paddling put-ins and take-outs with coordinates, access type, source, notes, and verification status. The owner's Google Maps list **Paddling · Paul** is a proposed input, but individual locations have **not yet been imported or verified**. Avoid publishing private or sensitive access locations without review.

## Status

Project setup and planning. No validated streamflow map or imported paddling locations yet.
