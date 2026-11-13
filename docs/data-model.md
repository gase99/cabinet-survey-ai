# Data model and invariants

## Core entities
User, Role, Session, Customer, Project, Site, Room, Wall, WallConnection, Element, Observation, SourceAsset, ReviewDecision, Approval, DrawingVersion, ExportJob, Delivery, SyncOperation and AuditEvent.

## Measurement fields
Each measurement stores integer `value_mm`, source type, source asset/region or manual author, optional confidence, review status, timestamps and revision. Unknown dimensions are null, never zero or inferred.

## Wall and element placement
Each wall has a stable ID, start/end coordinates, length, height, orientation and connectivity references. Elements refer to a host wall and named reference corner/direction, with along-wall offset, width, sill/base elevation, height and depth where applicable.

## Approval states
- `needs_review`: extracted or entered but not confirmed.
- `incomplete`: required fields missing or contradictory.
- `approved`: explicitly confirmed by an authorized user.

Approval is an auditable event. Editing an approved value creates a new revision and returns it to review.

## Geometry rules
All lengths in mm. Validate closure/connectivity, positive dimensions, element bounds, collisions and contradictory constraints. Store source observations separately from normalized geometry.
