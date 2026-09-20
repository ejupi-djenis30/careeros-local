"""Private error handling for agent transports, including validation failures."""

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse


class PrivateAgentRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                if request.method == "POST":
                    body = bytearray()
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > 266240:
                            raise HTTPException(
                                status_code=413,
                                detail={
                                    "code": "invalid_result",
                                    "message": "Request exceeds the agent byte limit",
                                },
                            )
                        body.extend(chunk)
                    request._body = bytes(body)
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse(
                    status_code=422,
                    content={
                        "detail": {
                            "code": "invalid_result",
                            "message": "Request does not satisfy the agent contract",
                        }
                    },
                )
            except HTTPException as exc:
                response = JSONResponse(
                    status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
                )
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            return response

        return handler
