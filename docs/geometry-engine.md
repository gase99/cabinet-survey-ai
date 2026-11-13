# Deterministic geometry engine

## Responsibility
Convert approved measurements and room topology into reproducible plan and wall-elevation geometry. No network or AI dependency is allowed inside the core geometry package.

## Coordinate conventions
- Integer millimetres.
- One project coordinate frame with documented origin and orientation.
- Wall start/end points and connectivity define topology.
- Elevation uses horizontal along-wall coordinate and vertical height from finished floor level.
- Element placement uses a named wall reference corner and validated offset.

## Validation
Positive dimensions; closed room boundary where required; connected endpoints within configured tolerance; no duplicate/zero-length edges; element bounds fit host wall; detect overlaps and conflicting openings/obstacles. Surface errors with entity IDs and actionable messages.

## Outputs
Top-down plan geometry, one elevation per wall, dimension annotations, legend, stable SVG/vector primitives and deterministic output for identical approved input.

## Testing
Golden fixtures for rectangles, L/U-shaped rooms, recesses, columns, doors/windows, utility points, invalid closures, overlaps and boundary violations.
