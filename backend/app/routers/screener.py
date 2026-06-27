from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import NaturalLanguageRequest, ScreeningRequest, ScreeningResult
from app.services.nl_parser import NaturalLanguageParser
from app.services.screener_service import ScreenerService

router = APIRouter(prefix="/api/screener", tags=["screener"])


@router.post("/run", response_model=ApiResponse[ScreeningResult])
def run(payload: ScreeningRequest, conn=Depends(get_db)) -> ApiResponse[ScreeningResult]:
    return ok(ScreenerService(conn).run(payload))


@router.post("/parse-and-run", response_model=ApiResponse[ScreeningResult])
def parse_and_run(payload: NaturalLanguageRequest, conn=Depends(get_db)) -> ApiResponse[ScreeningResult]:
    request = NaturalLanguageParser().parse(payload.text)
    return ok(ScreenerService(conn).run(request))
