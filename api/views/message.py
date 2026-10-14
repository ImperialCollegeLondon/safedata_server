from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import ServerMessage


class ServerMessageView(APIView):
    """Liveness handshake + optional configurable message for safedata
    clients to check on load.

    GET /api/message/
    """

    def get(self, request, *args, **kwargs):
        current = ServerMessage.current()
        message = current.message if current and current.message else None

        return Response({"status": "ok", "message": message})
