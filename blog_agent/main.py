import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI

from blog_agent.agent.blog_agent import BlogWorkflowService
from blog_agent.ws.server import SessionManager, create_router

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A FastAPI app with the websocket router and health endpoint mounted.

    Raises:
        RuntimeError: If the required OpenAI API key is missing.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required.")

    app = FastAPI(title="Blog Agent WebSocket")
    workflow = BlogWorkflowService()
    session_manager = SessionManager(workflow)
    app.include_router(create_router(session_manager))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
