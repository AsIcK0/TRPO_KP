from fastapi import APIRouter

from app.api.v1 import auth, correspondents, exports, files, health, incoming, reports, resolutions, users
from app.api.v1.dictionaries import departments_router, positions_router, types_router

api_router = APIRouter()
for module_router in (auth.router, users.router, departments_router, positions_router, types_router,
                      correspondents.router, incoming.router, resolutions.router, files.router,
                      reports.router, exports.router, health.router):
    api_router.include_router(module_router)
