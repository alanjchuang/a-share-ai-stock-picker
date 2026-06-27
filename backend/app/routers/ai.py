from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import (
    NaturalLanguageRequest,
    MarketPromptRequest,
    MarketPromptResponse,
    NewsAnalyzeRequest,
    NewsSentiment,
    OneClickRecommendRequest,
    ScreeningRequest,
    StockSelectionWorkflowResult,
    WebSearchRequest,
    WebSearchResponse,
    WorkflowRunRequest,
)
from app.services.market_prompt_service import MarketPromptService
from app.services.nl_parser import NaturalLanguageParser
from app.services.recommendation_jobs import get_one_click_recommendation_job, submit_one_click_recommendation_job
from app.services.sentiment_service import SentimentService
from app.services.stock_selection_workflow import StockSelectionWorkflow
from app.services.web_search_service import WebSearchService

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/parse", response_model=ApiResponse[ScreeningRequest])
def parse(payload: NaturalLanguageRequest) -> ApiResponse[ScreeningRequest]:
    return ok(NaturalLanguageParser().parse_ai(payload.text))


@router.get("/workflows", response_model=ApiResponse[list[dict[str, object]]])
def list_workflows(conn=Depends(get_db)) -> ApiResponse[list[dict[str, object]]]:
    return ok(StockSelectionWorkflow(conn).list_workflows())


@router.post("/stock-selection-workflow", response_model=ApiResponse[StockSelectionWorkflowResult])
def run_stock_selection_workflow(payload: WorkflowRunRequest, conn=Depends(get_db)) -> ApiResponse[StockSelectionWorkflowResult]:
    return ok(StockSelectionWorkflow(conn).run(payload))


@router.post("/recommendations/one-click", response_model=ApiResponse[dict[str, object]])
def one_click_recommend(payload: OneClickRecommendRequest) -> ApiResponse[dict[str, object]]:
    job = submit_one_click_recommendation_job(payload)
    message = "一键荐股已在后台启动" if job["accepted"] else job["message"]
    return ok(job, message)


@router.get("/recommendations/one-click/jobs/{job_id}", response_model=ApiResponse[dict[str, object]])
def one_click_recommend_job(job_id: int) -> ApiResponse[dict[str, object]]:
    job = get_one_click_recommendation_job(job_id)
    if job is None:
        raise ValueError("一键荐股任务不存在")
    return ok(job)


@router.post("/search", response_model=ApiResponse[WebSearchResponse])
def web_search(payload: WebSearchRequest) -> ApiResponse[WebSearchResponse]:
    return ok(WebSearchService().search(payload))


@router.post("/market-prompts", response_model=ApiResponse[MarketPromptResponse])
def market_prompts(payload: MarketPromptRequest) -> ApiResponse[MarketPromptResponse]:
    return ok(MarketPromptService().generate(payload), "市场情报Prompt已生成")


@router.post("/sentiment/analyze", response_model=ApiResponse[NewsSentiment])
def analyze(payload: NewsAnalyzeRequest, persist: bool = False, conn=Depends(get_db)) -> ApiResponse[NewsSentiment]:
    return ok(SentimentService(conn).analyze(payload, persist=persist))


@router.post("/sentiment/refresh", response_model=ApiResponse[dict[str, int]])
def refresh(conn=Depends(get_db)) -> ApiResponse[dict[str, int]]:
    return ok(SentimentService(conn).batch_refresh_existing())
