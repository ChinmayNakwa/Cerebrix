# backend/database/postgres.py

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from backend.config import settings

# Connection configuration
connection_kwargs = {
    "autocommit": True,
    "prepare_threshold": 0,
}

# Initialize the pool with open=False to prevent warnings.
# We will explicitly open it in app.py
pool = AsyncConnectionPool(
    conninfo=settings.POSTGRES_DB_URL,
    max_size=20,
    kwargs=connection_kwargs,
    open=False 
)

# Initialize the checkpointer with the pool
checkpointer = AsyncPostgresSaver(pool)

async def delete_thread_data(thread_id: str):
    """
    Deletes all checkpoint data associated with a specific thread_id.
    """
    # Clears checkpoints, checkpoint_writes and checkpoint_blobs (where the messages themselves live)
    await checkpointer.adelete_thread(thread_id)