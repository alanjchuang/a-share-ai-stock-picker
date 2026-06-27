from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import AnalysisReportOut
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("", response_model=ApiResponse[list[AnalysisReportOut]])
def list_reports(limit: int = 30, conn=Depends(get_db)) -> ApiResponse[list[AnalysisReportOut]]:
    return ok(ReportService(conn).list_reports(limit=limit))


@router.post("/daily", response_model=ApiResponse[AnalysisReportOut])
def generate_daily(conn=Depends(get_db)) -> ApiResponse[AnalysisReportOut]:
    return ok(ReportService(conn).generate_daily_report(), "复盘报告已生成")


@router.get("/{report_id}", response_model=ApiResponse[AnalysisReportOut])
def get_report(report_id: int, conn=Depends(get_db)) -> ApiResponse[AnalysisReportOut]:
    return ok(ReportService(conn).get_report(report_id))
