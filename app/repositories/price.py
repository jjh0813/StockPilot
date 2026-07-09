"""시세·재무·일봉 조회 (pykrx). 별도 API 키 불필요."""


async def get_ohlcv(ticker: str, start: str, end: str):
    ...  # TODO: 일봉 OHLCV


async def get_fundamentals(ticker: str):
    ...  # TODO: PER/PBR 등 재무 지표
