"""
Repopulate ChromaDB from SQLite.

Use this when your notes exist in notes.db but the vector store is empty
or out of date — e.g. after copying notes.db to a new machine, deleting
the Chroma persist directory, or changing the embedding model.

Usage:
    python sync.py

This calls the embedding API once per active note, so it consumes Gemini
quota proportional to your note count. Only run it when you need to.
"""

import sys

from app import create_app
from app.extensions import db
from app.models import Note
from vector_store import sync_notes_to_chroma


def main():
    app = create_app()

    with app.app_context():
        active = db.session.scalars(
            db.select(Note).where(Note.in_bin != True)  # noqa: E712
        ).all()

        if not active:
            print("No active notes to sync.")
            return 0

        print(f"Syncing {len(active)} active note(s) to ChromaDB...")
        print("This will call the embedding API per note. Starting...")

        try:
            synced, failed = sync_notes_to_chroma(db.session, Note)
        except Exception as e:
            print(f"\nSync aborted: {e}", file=sys.stderr)
            return 1

        print(f"Done. Synced {synced}/{len(active)} notes.")
        if failed:
            print(
                f"WARNING: {failed} note(s) failed to sync. "
                "Check logs for details and re-run.",
                file=sys.stderr,
            )
            return 1

        return 0


if __name__ == "__main__":
    sys.exit(main())