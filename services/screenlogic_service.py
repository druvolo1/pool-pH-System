import asyncio, logging
from screenlogicpy import ScreenLogicGateway
from utils.settings_utils import load_settings
from status_namespace import emit_status_update   # already exists
logger = logging.getLogger(__name__)

class ScreenLogicService:
    def __init__(self):
        self._gateway = ScreenLogicGateway()
        self._task = None

    def start(self):
        if not self._task:
            self._task = asyncio.create_task(self._runner())

    async def _runner(self):
        while True:
            try:
                cfg = load_settings().get("screenlogic", {})
                if not cfg.get("enabled"):
                    await asyncio.sleep(10)
                    continue

                await self._gateway.async_connect(cfg["host"])
                await self._gateway.async_update()

                data = {
                    "water_temp" : self._gateway.get_pool_temp(),
                    "air_temp"   : self._gateway.get_air_temp(),
                    "ph"         : self._gateway.get_ph(),
                }
                emit_status_update({"screenlogic": data})
                logger.debug("ScreenLogic: %s", data)

            except Exception as exc:
                logger.warning("ScreenLogic poll failed: %s", exc)

            await asyncio.sleep(cfg.get("poll_interval", 30))

# single global instance
screenlogic_service = ScreenLogicService()
