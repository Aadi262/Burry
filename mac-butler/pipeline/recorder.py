"""pipeline/recorder.py — Memory recording extracted from butler.py (stub).

Full extraction requires moving ConversationContext and its associated globals.
This stub satisfies the pipeline/ module structure.
The real _record() implementation remains in butler.py pending full migration.

TODO: Move ConversationContext, _SESSION_CONVERSATION, _LEARNING_TRACE_LOCK,
      _LAST_RESOLVED_COMMAND, _record(), _remember_conversation_turn(),
      _remember_project_state() here as next step.
"""

# Placeholder — re-exports from butler once the migration is complete.
# Called as: from pipeline.recorder import record as record_turn
def record(*args, **kwargs):  # type: ignore[override]
    """Stub: delegates to butler._record at runtime to avoid circular import during migration."""
    import butler  # noqa: PLC0415
    return butler._record(*args, **kwargs)
