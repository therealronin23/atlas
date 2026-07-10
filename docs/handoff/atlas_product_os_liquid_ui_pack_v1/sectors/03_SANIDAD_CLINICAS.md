# Sanidad / clínicas

## Domain objects

paciente, cita, informe, prueba, consentimiento, receta, historial

## Frequent workflows

agenda, triaje, seguimiento, informes, facturación

## Liquid workbenches

Patient Timeline, Clinical Notes, Consent Gate, Appointment Flow

## Gates

- Human Review Gate
- Outbound Gate when sending/publishing
- Cloud Data Gate for sensitive data
- Delete Gate for destructive actions
- Sector-specific Gate where relevant

## Business Core mapping

This sector must map its core entities to Atlas Business Core if the user has no external CRM/ERP, or to Legacy Link Layer if an external system exists.

## Question pack requirement

Questions must be concrete, closed-option where possible, validated and adaptive. Avoid vague open prompts.
