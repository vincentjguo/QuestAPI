import secrets
from contextlib import ContextDecorator

from api.scraper import common
from api.scraper.common import delete_session


class TokenManager(ContextDecorator):

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        delete_session(self.token)
        return False

    def __init__(self, token=secrets.token_urlsafe(16)):
        self.token = token

    def __str__(self):
        return self.token

    def __repr__(self):
        return self.token

    def create_from_existing_user(self, user: str):
        self.token = common.known_users[user]

    def verify_token(self) -> bool:
        return self.token in common.known_users.values()

    def set_token(self, token: str) -> None:
        self.token = token

    def get_token(self) -> str:
        return self.token

    def __del__(self):
        delete_session(self.token)
