from curl_cffi.requests import AsyncSession

class BaseSession:
    def __init__(
        self, 
        max_clients: int=50,
        timeout: int=120,
    ):
        self.session = AsyncSession(
            max_clients=max_clients,
            impersonate='chrome120',
            retry=3,
            timeout=timeout
        )
    def get_session(self) -> AsyncSession:
        return self.session
    
    async def close(self):
        await self.session.close()

base_session = BaseSession()