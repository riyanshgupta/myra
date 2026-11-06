
from curl_cffi.requests import AsyncSession


class BaseClient:
    def __init__(self, session: AsyncSession):
        self.session = session
