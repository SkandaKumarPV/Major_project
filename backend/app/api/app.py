
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.core.config import Settings
from backend.app.services.livekit_service import LiveKitService


logger = logging.getLogger("ai-interviewer-api")


class InterviewSessionResponse(BaseModel):
    livekit_url: str
    room_name: str
    participant_identity: str
    token: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_environment()
    service = LiveKitService(settings)

    app.state.livekit_service = service

    try:
        yield
    finally:
        await service.close()


app = FastAPI(
    title="Simple AI Interviewer API",
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post(
    "/api/interviews",
    response_model=InterviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview(request: Request):
    service = request.app.state.livekit_service

    try:
        session = await service.create_session()
        return session

    except Exception as exc:
        logger.exception("Failed to create interview session")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to create the LiveKit interview session.",
        ) from exc


@app.post(
    "/api/interviews/{room_name}/dispatch",
    status_code=status.HTTP_202_ACCEPTED,
)
async def dispatch_interviewer(room_name: str, request: Request):
    service = request.app.state.livekit_service

    try:
        dispatched = await service.dispatch_agent(room_name)

        return {
            "room_name": room_name,
            "agent_name": service.agent_name,
            "dispatched": dispatched,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Failed to dispatch interviewer")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to dispatch the interviewer.",
        ) from exc


@app.delete(
    "/api/interviews/{room_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def end_interview(room_name: str, request: Request):
    service = request.app.state.livekit_service

    try:
        await service.end_session(room_name)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Failed to end interview session")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to end the LiveKit interview session.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
