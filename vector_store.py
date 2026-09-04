import os
import logging
from typing import List, Optional, Dict, Any
import chromadb

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_DATA_PATH = os.path.join(BASE_DIR, "instance", "chroma_db")

DEFAULT_DISTANCE_THRESHOLD = 0.65

_client: Optional[chromadb.PersistentClient] = None


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        os.makedirs(CHROMA_DATA_PATH, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
    return _client


def get_user_collection(user_id: int):
    client = get_chroma_client()
    collection_name = f"user_{user_id}_notes"
    return client.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )


def prepare_note_document(note) -> str:
    """Prepares text document representation for vector embedding."""
    title = (note.title or "").strip()
    tags = ""
    summary = ""
    if isinstance(note.meta_data, dict):
        tags_list = note.meta_data.get("tags", [])
        if isinstance(tags_list, list):
            tags = " ".join(tags_list)
        summary = str(note.meta_data.get("summary", "") or "")
    md_content = (note.md_content or "").strip()
    return f"Title: {title}\nTags: {tags}\nSummary: {summary}\nContent: {md_content}"


def upsert_note_vector(note) -> bool:
    """Upsert note document into user's Chroma collection."""
    if not note or not getattr(note, "user_id", None) or getattr(note, "in_bin", False):
        return False
    try:
        collection = get_user_collection(note.user_id)
        document_text = prepare_note_document(note)
        collection.upsert(
            ids=[str(note.id)],
            documents=[document_text],
            metadatas=[
                {
                    "note_id": note.id,
                    "title": str(note.title or ""),
                    "user_id": note.user_id,
                }
            ],
        )
        logger.info(
            "[vector_store] Successfully upserted note_id=%s for user_id=%s",
            note.id,
            note.user_id,
        )
        return True
    except Exception as e:
        logger.exception(
            "[vector_store] Failed to upsert note_id=%s for user_id=%s: %s",
            getattr(note, "id", None),
            getattr(note, "user_id", None),
            e,
        )
        return False


def delete_note_vector(note_id: int, user_id: int) -> bool:
    """Delete note document from user's Chroma collection."""
    if not note_id or not user_id:
        return False
    try:
        collection = get_user_collection(user_id)
        collection.delete(ids=[str(note_id)])
        logger.info(
            "[vector_store] Deleted note_id=%s from vector store for user_id=%s",
            note_id,
            user_id,
        )
        return True
    except Exception as e:
        logger.exception(
            "[vector_store] Failed to delete note_id=%s for user_id=%s: %s",
            note_id,
            user_id,
            e,
        )
        return False


def search_notes_vector(
    topic: str,
    user_id: int,
    n_results: int = 3,
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    Searches the user's notes using ChromaDB vector similarity.
    Returns:
      {
        "note_ids": ["1", "2"],  # matching note IDs that pass distance_threshold
        "msg": None or "I could not find your notes about 'topic'."
      }
    """
    topic_str = (topic or "").strip()
    if not topic_str:
        return {
            "note_ids": [],
            "msg": "No search topic provided.",
        }

    try:
        collection = get_user_collection(user_id)
        count = collection.count()
        if count == 0:
            return {
                "note_ids": [],
                "msg": f"I could not find your notes about {topic_str}.",
            }

        k = min(n_results, count)
        results = collection.query(
            query_texts=[topic_str],
            n_results=k,
            include=["distances", "metadatas"],
        )

        matched_ids = []
        if (
            results
            and "ids" in results
            and results["ids"]
            and len(results["ids"][0]) > 0
        ):
            ids_list = results["ids"][0]
            distances = results.get("distances", [[]])[0]

            for note_id_str, dist in zip(ids_list, distances):
                logger.debug(
                    "[vector_store] Candidate note_id=%s distance=%s (threshold=%s)",
                    note_id_str,
                    dist,
                    distance_threshold,
                )
                if dist <= distance_threshold:
                    matched_ids.append(note_id_str)

        if not matched_ids:
            return {
                "note_ids": [],
                "msg": f"I could not find your notes about {topic_str}.",
            }

        return {
            "note_ids": matched_ids,
            "msg": None,
        }

    except Exception as e:
        logger.exception(
            "[vector_store] Error searching notes for user_id=%s with query='%s': %s",
            user_id,
            topic_str,
            e,
        )
        return {
            "note_ids": [],
            "msg": "An error occurred while searching your notes with vector database.",
            "error": True,
        }


from sqlalchemy import select


def sync_notes_to_chroma(db_session, NoteModel):
    """Sync all active notes in SQLite to Chroma on startup."""
    try:
        active_notes = db_session.scalars(
            select(NoteModel).where(NoteModel.in_bin != True)
        ).all()
        synced = 0
        for note in active_notes:
            if upsert_note_vector(note):
                synced += 1
        logger.info(
            "[vector_store] Successfully synced %d active notes to ChromaDB.", synced
        )
    except Exception as e:
        logger.exception("[vector_store] Error during sync_notes_to_chroma: %s", e)
