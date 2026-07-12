# Atlas Product OS / Liquid UI Pack v1

Created: 2026-07-10T19:27:05

This pack is the product, UX, architecture, integration, business-core and safety handoff for the next Fable phase.

It exists because the previous implementation proved a technical base, but not Atlas as a product. The current web shell is a validation harness. Atlas itself must become an objective-driven cognitive OS with liquid workbenches, native presence, sector models, governed integrations, and a native business core.

## Non-negotiable definition

```text
Atlas = Cognitive OS orientado a objetivos, sectores y workbenches líquidos.
```

The basic unit is:

```text
Objetivo → Sector → Datos → Liquid Workbench → Validación → Acción auditada → Memoria
```

## Core axioms

```text
La interfaz de Atlas no es una pantalla.
Es la forma temporal que toma Atlas para resolver un objetivo.

Atlas no abre aplicaciones.
Atlas crea el entorno necesario para cumplir un objetivo.

Atlas no tiene animaciones.
Atlas tiene comportamiento visible.

El grafo no es una pantalla.
El grafo es la materia visual de Atlas.

La web actual es validation harness, no UX final.

Local by default.
Cloud by necessity.
Audit always.
No silent outbound.
No silent certificate use.
Conectar debe ser fácil.
Actuar debe ser gobernado.
```

## How to use this pack

1. Read this file fully.
2. Read `tasks/FABLE_EXECUTION_ORDER.md`.
3. Read `tasks/DO_NOT_DO.md`.
4. Read `product/00_ATLAS_PRODUCT_CONSTITUTION.md`.
5. Read `research/00_RESEARCH_INDEX.md`.
6. Do not implement new UX until `design/00_ATLAS_UX_CONSTITUTION.md`, `design/01_GLOBAL_APP_ANATOMY.md`, and `design/17_UI_QUALITY_GATE.md` are internalized.
7. Do not implement integrations until `product/20_INTEGRATION_FABRIC.md`, `product/24_CONNECTION_STORE.md`, and `product/30_ATLAS_BUSINESS_CORE.md` are internalized.
8. Every implementation phase must end by writing continuation files using the templates in `continuation/`.

## Critical direction for Fable

You are invited to improve this pack, but not to dilute it.

You must improve by identifying gaps, contradictions, simplifications, risks and better designs. You must not improve by replacing Atlas with a generic dashboard, chat app, automation clone, CRM clone, ERP clone, n8n clone, Jarvis clone or SaaS template.

If a decision conflicts with the constitution, stop and write an ADR proposal before implementing.
