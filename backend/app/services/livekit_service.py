
import asyncio
import logging
import uuid

from livekit import api

from backend.app.core.config import Settings


logger = logging.getLogger("ai-interviewer-livekit")


class LiveKitService:
    def __init__(self, settings: Settings):
        if not settings.livekit_url:
            raise ValueError("LiveKit URL is required")

        if not settings.livekit_api_key:
            raise ValueError("LiveKit API key is required")

        if not settings.livekit_api_secret:
            raise ValueError("LiveKit API secret is required")

        if not settings.agent_name:
            raise ValueError("LiveKit agent name is required")

        self.livekit_url = settings.livekit_url
        self.api_key = settings.livekit_api_key
        self.api_secret = settings.livekit_api_secret
        self.agent_name = settings.agent_name

        self.client = api.LiveKitAPI(
            url=self.livekit_url,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

        self._dispatched_rooms: set[str] = set()
        self._dispatch_lock = asyncio.Lock()

    async def create_session(self) -> dict:
        room_id = str(uuid.uuid4())
        room_name = f"interview-{room_id}"
        participant_identity = str(uuid.uuid4())

        await self.client.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                empty_timeout=300,
                max_participants=2,
            )
        )

        try:
            token = (
                api.AccessToken(self.api_key, self.api_secret)
                .with_identity(participant_identity)
                .with_name("Candidate")
                .with_grants(
                    api.VideoGrants(
                        room_join=True,
                        room=room_name,
                        can_publish=True,
                        can_subscribe=True,
                    )
                )
                .to_jwt()
            )

        except Exception:
            # Do not leave an unused room behind if token creation fails.
            try:
                await self.client.room.delete_room(
                    api.DeleteRoomRequest(room=room_name)
                )
            except Exception:
                logger.exception(
                    "Could not clean up room after token creation failed"
                )

            raise

        return {
            "livekit_url": self.livekit_url,
            "room_name": room_name,
            "participant_identity": participant_identity,
            "token": token,
        }

    async def dispatch_agent(self, room_name: str) -> bool:
        """
        Explicitly dispatch the interviewer to a candidate-connected room.

        Returns True for a new dispatch and False if already dispatched
        by this API process.
        """
        if not room_name.startswith("interview-"):
            raise ValueError("Invalid interview room name")

        async with self._dispatch_lock:
            if room_name in self._dispatched_rooms:
                return False

            await self.client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=self.agent_name,
                    room=room_name,
                )
            )

            self._dispatched_rooms.add(room_name)

            return True

    async def end_session(self, room_name: str):
        if not room_name.startswith("interview-"):
            raise ValueError("Invalid interview room name")

        await self.client.room.delete_room(
            api.DeleteRoomRequest(room=room_name)
        )

        self._dispatched_rooms.discard(room_name)

    async def close(self):
        await self.client.aclose()
