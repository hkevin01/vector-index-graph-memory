"""Neo4j repository layer for schema, writes, and retrieval."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from neo4j import GraphDatabase

from app.config import Settings
from app.models.schemas import ContextEntity, ContextResponse, RelationCandidate, ResolutionDecision, StatsResponse
from app.services.resolution import ExistingEntity


class GraphRepository:
    """Purpose: Persist all memory tiers and identity edges into Neo4j.

    Inputs: Structured payloads from the application services.
    Outputs: Query results, graph statistics, and context payloads.
    Preconditions: Neo4j is reachable with vector index support.
    Postconditions: Schema exists before data writes occur.
    Failure modes: Driver and Cypher errors surface to the caller.
    """

    def __init__(self, settings: Settings) -> None:
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        self.embedding_dimensions = settings.embedding_dimensions

    def close(self) -> None:
        with suppress(Exception):
            self.driver.close()

    def ping(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    def ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT conversation_id IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT trace_id IF NOT EXISTS FOR (t:ReasoningTrace) REQUIRE t.id IS UNIQUE",
            "CREATE VECTOR INDEX entity_embedding_index IF NOT EXISTS FOR (e:Entity) ON (e.embedding) OPTIONS {indexConfig: {`vector.dimensions`: %d, `vector.similarity_function`: 'cosine'}}"
            % self.embedding_dimensions,
            "CREATE VECTOR INDEX message_embedding_index IF NOT EXISTS FOR (m:Message) ON (m.embedding) OPTIONS {indexConfig: {`vector.dimensions`: %d, `vector.similarity_function`: 'cosine'}}"
            % self.embedding_dimensions,
        ]
        with self.driver.session() as session:
            for statement in statements:
                session.run(statement).consume()

    def get_or_create_conversation(self, session_id: str) -> str:
        conversation_id = f"conversation:{session_id}"
        with self.driver.session() as session:
            session.run(
                """
                MERGE (c:Conversation {id: $id})
                ON CREATE SET c.session_id = $session_id, c.created_at = datetime()
                RETURN c.id AS id
                """,
                id=conversation_id,
                session_id=session_id,
            ).single()
        return conversation_id

    def create_message(self, session_id: str, role: str, content: str, embedding: list[float]) -> str:
        message_id = str(uuid4())
        conversation_id = self.get_or_create_conversation(session_id)
        with self.driver.session() as session:
            session.run(
                """
                MATCH (c:Conversation {id: $conversation_id})
                OPTIONAL MATCH (c)-[:HAS_MESSAGE]->(last:Message)
                WHERE NOT (last)-[:NEXT]->(:Message)
                CREATE (m:Message {
                    id: $message_id,
                    role: $role,
                    content: $content,
                    embedding: $embedding,
                    created_at: datetime()
                })
                MERGE (c)-[:HAS_MESSAGE]->(m)
                FOREACH (_ IN CASE WHEN last IS NULL THEN [] ELSE [1] END |
                    MERGE (last)-[:NEXT]->(m)
                )
                RETURN m.id AS id
                """,
                conversation_id=conversation_id,
                message_id=message_id,
                role=role,
                content=content,
                embedding=embedding,
            ).single()
        return message_id

    def find_existing_entities(self, entity_type: str) -> list[ExistingEntity]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.entity_type = $entity_type
                RETURN e.id AS id, e.name AS name, coalesce(e.aliases, []) AS aliases, e.embedding AS embedding, e.entity_type AS entity_type
                """,
                entity_type=entity_type,
            )
            return [ExistingEntity(**record.data()) for record in result]

    def create_entity(self, candidate: dict[str, Any], embedding: list[float]) -> str:
        entity_id = str(uuid4())
        labels = self._safe_labels(candidate["entity_type"])
        query = f"""
        CREATE (e:Entity:{labels} {{
            id: $id,
            name: $name,
            canonical_name: $canonical_name,
            entity_type: $entity_type,
            description: $description,
            aliases: $aliases,
            embedding: $embedding,
            created_at: datetime()
        }})
        RETURN e.id AS id
        """
        with self.driver.session() as session:
            session.run(
                query,
                id=entity_id,
                name=candidate["name"],
                canonical_name=candidate["name"],
                entity_type=candidate["entity_type"],
                description=candidate["description"],
                aliases=candidate["aliases"],
                embedding=embedding,
            ).single()
        return entity_id

    def merge_entity(self, entity_id: str, candidate: dict[str, Any]) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MATCH (e:Entity {id: $entity_id})
                SET e.aliases = coalesce(e.aliases, []) + [alias IN $aliases WHERE NOT alias IN coalesce(e.aliases, [])],
                    e.description = CASE
                        WHEN size(coalesce(e.description, '')) >= size($description) THEN e.description
                        ELSE $description
                    END,
                    e.updated_at = datetime()
                """,
                entity_id=entity_id,
                aliases=candidate["aliases"],
                description=candidate["description"],
            ).consume()

    def create_pending_same_as(
        self,
        left_id: str,
        right_id: str,
        confidence: float,
        method: str,
    ) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MATCH (left:Entity {id: $left_id}), (right:Entity {id: $right_id})
                MERGE (left)-[r:SAME_AS]->(right)
                SET r.confidence = $confidence,
                    r.status = 'pending',
                    r.method = $method,
                    r.created_at = datetime()
                """,
                left_id=left_id,
                right_id=right_id,
                confidence=confidence,
                method=method,
            ).consume()

    def connect_message_mentions(self, message_id: str, entity_ids: list[str]) -> None:
        if not entity_ids:
            return
        with self.driver.session() as session:
            session.run(
                """
                MATCH (m:Message {id: $message_id})
                UNWIND $entity_ids AS entity_id
                MATCH (e:Entity {id: entity_id})
                MERGE (m)-[:MENTIONS]->(e)
                """,
                message_id=message_id,
                entity_ids=entity_ids,
            ).consume()

    def connect_entities(self, relations: list[RelationCandidate], resolved_ids: dict[str, str]) -> None:
        if not relations:
            return
        with self.driver.session() as session:
            for relation in relations:
                left_id = resolved_ids.get(relation.source_name.casefold())
                right_id = resolved_ids.get(relation.target_name.casefold())
                if not left_id or not right_id:
                    continue
                session.run(
                    """
                    MATCH (left:Entity {id: $left_id}), (right:Entity {id: $right_id})
                    MERGE (left)-[r:RELATED_TO {type: $relation_type}]->(right)
                    SET r.updated_at = datetime()
                    """,
                    left_id=left_id,
                    right_id=right_id,
                    relation_type=relation.relationship_type,
                ).consume()

    def create_reasoning_trace(self, message_id: str, query: str, touched_entity_ids: list[str]) -> None:
        trace_id = str(uuid4())
        step_id = str(uuid4())
        with self.driver.session() as session:
            session.run(
                """
                MATCH (m:Message {id: $message_id})
                CREATE (t:ReasoningTrace {id: $trace_id, query: $query, success: true, created_at: datetime()})
                CREATE (s:ReasoningStep {id: $step_id, sequence: 1, kind: 'retrieval', content: 'Hybrid graph retrieval executed.'})
                MERGE (t)-[:INITIATED_BY]->(m)
                MERGE (t)-[:HAS_STEP]->(s)
                WITH t
                UNWIND $entity_ids AS entity_id
                MATCH (e:Entity {id: entity_id})
                MERGE (t)-[:TOUCHED]->(e)
                """,
                trace_id=trace_id,
                step_id=step_id,
                message_id=message_id,
                query=query,
                entity_ids=touched_entity_ids,
            ).consume()

    def build_context(self, query: str, session_id: str, embedding: list[float], limit: int = 5) -> ContextResponse:
        with self.driver.session() as session:
            message_hits = [
                record["content"]
                for record in session.run(
                    """
                    CALL db.index.vector.queryNodes('message_embedding_index', $limit, $embedding)
                    YIELD node, score
                    MATCH (c:Conversation)-[:HAS_MESSAGE]->(node)
                    WHERE c.session_id = $session_id
                    RETURN node.content AS content
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                    embedding=embedding,
                    session_id=session_id,
                )
            ]

            entity_records = session.run(
                """
                CALL db.index.vector.queryNodes('entity_embedding_index', $limit, $embedding)
                YIELD node, score
                OPTIONAL MATCH (node)-[r:RELATED_TO]->(neighbor:Entity)
                RETURN node.id AS id,
                       node.name AS name,
                       node.entity_type AS entity_type,
                       score AS score,
                       collect(DISTINCT neighbor.name)[0..5] AS related_names
                ORDER BY score DESC
                LIMIT $limit
                """,
                limit=limit,
                embedding=embedding,
            )
            entities = [ContextEntity(**record.data()) for record in entity_records]

            reasoning = [
                record["query"]
                for record in session.run(
                    """
                    MATCH (t:ReasoningTrace)-[:TOUCHED]->(e:Entity)
                    WHERE e.name IN $entity_names
                    RETURN DISTINCT t.query AS query
                    ORDER BY query ASC
                    LIMIT $limit
                    """,
                    entity_names=[entity.name for entity in entities],
                    limit=limit,
                )
            ]

        return ContextResponse(
            query=query,
            session_id=session_id,
            message_hits=message_hits,
            entities=entities,
            reasoning=reasoning,
        )

    def review_duplicate(self, left_id: str, right_id: str, confirm: bool, reviewer: str) -> None:
        with self.driver.session() as session:
            if confirm:
                session.run(
                    """
                    MATCH (left:Entity {id: $left_id})-[r:SAME_AS]->(right:Entity {id: $right_id})
                    SET r.status = 'confirmed',
                        r.reviewed_by = $reviewer,
                        r.reviewed_at = datetime()
                    SET left.aliases = coalesce(left.aliases, [])
                        + [alias IN coalesce(right.aliases, []) WHERE NOT alias IN coalesce(left.aliases, [])]
                        + CASE WHEN right.name IN coalesce(left.aliases, []) THEN [] ELSE [right.name] END,
                        left.description = CASE
                            WHEN size(coalesce(left.description, '')) >= size(coalesce(right.description, '')) THEN left.description
                            ELSE right.description
                        END,
                        left.updated_at = datetime()
                    """,
                    left_id=left_id,
                    right_id=right_id,
                    reviewer=reviewer,
                ).consume()
                return

            session.run(
                """
                MATCH (:Entity {id: $left_id})-[r:SAME_AS]->(:Entity {id: $right_id})
                SET r.status = 'rejected',
                    r.reviewed_by = $reviewer,
                    r.reviewed_at = datetime()
                """,
                left_id=left_id,
                right_id=right_id,
                reviewer=reviewer,
            ).consume()

    def stats(self) -> StatsResponse:
        with self.driver.session() as session:
            record = session.run(
                """
                CALL {
                    MATCH (:Conversation) RETURN count(*) AS conversations
                }
                CALL {
                    MATCH (:Message) RETURN count(*) AS messages
                }
                CALL {
                    MATCH (:Entity) RETURN count(*) AS entities
                }
                CALL {
                    MATCH (:ReasoningTrace) RETURN count(*) AS traces
                }
                CALL {
                    MATCH ()-[r:SAME_AS {status: 'pending'}]->() RETURN count(r) AS pending_duplicates
                }
                RETURN conversations, messages, entities, traces, pending_duplicates
                """
            ).single()
        assert record is not None
        return StatsResponse(
            conversations=record["conversations"],
            messages=record["messages"],
            entities=record["entities"],
            traces=record["traces"],
            pending_duplicates=record["pending_duplicates"],
            checked_at=datetime.now(tz=UTC),
        )

    @staticmethod
    def _safe_labels(entity_type: str) -> str:
        return "".join(character for character in entity_type.title() if character.isalnum())
