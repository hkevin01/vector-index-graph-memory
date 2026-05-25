# Architecture

## Core idea

The project treats vector similarity as a signal, not as identity. Identity lives in the graph.

## Memory tiers

- Short-term memory: `Conversation` and `Message`
- Long-term memory: `Entity` nodes with POLE+O labels and `RELATED_TO` edges
- Reasoning memory: `ReasoningTrace` and `ReasoningStep`

## Deduplication gate

- `score >= 0.95`: merge into the canonical node
- `0.85 <= score < 0.95`: create pending `SAME_AS`
- `score < 0.85`: keep a new node

## Retrieval shape

The retrieval query is designed to combine:

- semantic message matches
- semantic entity matches
- graph neighbors reached through typed relationships
- provenance edges back to the originating messages and traces
