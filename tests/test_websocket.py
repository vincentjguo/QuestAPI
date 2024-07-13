import asyncio
import json
from unittest import mock, IsolatedAsyncioTestCase
from unittest.mock import call

import websockets
from websockets import WebSocketServerProtocol

from api.session_manager import SessionManager, SessionException
from api.websocket import process_requests, WebsocketResponseCode, WEBSOCKET_TIMEOUT


class TestWebsocket(IsolatedAsyncioTestCase):
    mock_socket = mock.AsyncMock(spec=WebSocketServerProtocol)
    mock_session = mock.AsyncMock(spec=SessionManager)

    async def test_process_requests_search(self):
        expected_value = "Math 239 - AAAH"
        self.mock_socket.recv.side_effect = ["SEARCH", "1245", "math", "239", "QUIT"]
        self.mock_session.handle_search_classes.return_value = expected_value

        await process_requests(self.mock_socket, self.mock_session)

        self.mock_socket.send.assert_called_with(json.dumps(
            {"status": WebsocketResponseCode.SUCCESS.value, "payload": expected_value}
        ))

        self.mock_socket.close.assert_called()

    async def test_process_requests_search_exception(self):
        error_msg = "Timeout Error"
        self.mock_socket.recv.side_effect = ["SEARCH", "1245", "math", "239", "QUIT"]
        self.mock_session.handle_search_classes.side_effect = SessionException(error_msg)

        await process_requests(self.mock_socket, self.mock_session)

        self.mock_socket.send.assert_called_with(json.dumps(
            {"status": WebsocketResponseCode.ERROR.value, "payload": error_msg}
        ))

        self.mock_socket.close.assert_called()


    async def test_process_requests_search_timeout(self):
        # self.mock_socket.recv.side_effect = call(lambda: return "SEARCH") ["SEARCH", "1245", "math", asyncio.Future(), "QUIT"]

        await process_requests(self.mock_socket, self.mock_session)

        self.mock_socket.send.assert_called_with(json.dumps(
            {"status": WebsocketResponseCode.ERROR.value, "payload": str(TimeoutError)}
        ))

        self.mock_socket.close.assert_called()
