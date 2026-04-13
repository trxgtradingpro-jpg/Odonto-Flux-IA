from fastapi import Query


def pagination_params(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> tuple[int, int]:
    return limit, offset
