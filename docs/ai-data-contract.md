# AI extraction contract

## Input
Annotated sketch image plus optional user notes and language hints; optional speech-to-text transcript; explicit project context, known units and confirmed reference facts.

## Output
Return structured candidate observations only: detected entity/type, transcription and normalized candidate value, candidate unit, evidenced wall/reference corner, source image polygon/bounding box, confidence, uncertainty explanation, missing fields and clarification questions.

## Hard rules
- Never infer real dimensions from visual proportions or pixel distance.
- Never invent a wall length, offset, height, unit or corner association.
- Preserve original OCR/transcription and normalized interpretation separately.
- Mark uncertain Persian/Arabic numerals, decimal separators, arrows and handwritten labels for review.
- Confidence never authorizes approval.
- AI must not produce final drawing coordinates or bypass geometry validation.

## Review flow
Image correction -> OCR/Vision candidates -> ambiguity detection -> overlay review UI -> user correction -> explicit approval -> deterministic geometry engine.
