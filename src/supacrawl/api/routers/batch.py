"""Batch scrape endpoints; async job lifecycle with background processing."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from supacrawl.api.auth import get_api_key
from supacrawl.api.dependencies import get_scrape_service
from supacrawl.api.jobs import JobStatus, JobStore, MaxJobsExceededError
from supacrawl.api.models.batch import (
    BatchScrapeCreateResponse,
    BatchScrapeRequest,
    BatchScrapeStatusResponse,
)
from supacrawl.api.models.common import ErrorResponse
from supacrawl.api.models.scrape import ScrapeRequest
from supacrawl.api.routers.scrape import _build_service_kwargs, _scrape_result_to_response
from supacrawl.services import ScrapeService

logger = logging.getLogger("supacrawl.api.batch")

router = APIRouter()


def _get_job_store(request: Request) -> JobStore:
    """Retrieve the ``JobStore`` from application state."""
    return request.app.state.job_store


def _batch_request_to_scrape_request(req: BatchScrapeRequest, url: str) -> ScrapeRequest:
    """Build a ``ScrapeRequest`` from a batch request for a single URL.

    Copies the flat scrape options from the batch request into a
    ``ScrapeRequest`` with the given URL.
    """
    return ScrapeRequest(
        url=url,
        formats=req.formats,
        only_main_content=req.only_main_content,
        wait_for=req.wait_for,
        timeout=req.timeout,
        include_tags=req.include_tags,
        exclude_tags=req.exclude_tags,
        mobile=req.mobile,
        actions=req.actions,
        location=req.location,
        headers=req.headers,
        max_age=req.max_age,
        proxy=req.proxy,
        store_in_cache=req.store_in_cache,
    )


def _scrape_data_to_dict(result: Any) -> dict[str, Any]:
    """Convert a ``ScrapeResult`` to a v2-compatible camelCase dict."""
    response = _scrape_result_to_response(result)
    if response.data is None:
        return {}
    return response.data.model_dump(by_alias=True, exclude_none=True)


async def _run_batch_scrape(
    job_id: str,
    job_store: JobStore,
    scrape_service: ScrapeService,
    req: BatchScrapeRequest,
) -> None:
    """Background task that scrapes each URL and updates the job."""
    try:
        for url in req.urls:
            job = job_store._jobs.get(job_id)
            if job is None or job.status == JobStatus.cancelled:
                logger.info("Job %s cancelled; stopping batch scrape", job_id)
                return

            scrape_req = _batch_request_to_scrape_request(req, url)
            kwargs = _build_service_kwargs(scrape_req)

            try:
                result = await scrape_service.scrape(url=url, **kwargs)
                page_dict = _scrape_data_to_dict(result)
                job.data.append(page_dict)
            except Exception:
                logger.exception("Error scraping %s in batch job %s", url, job_id)
                job.data.append({"error": f"Failed to scrape {url}"})

            job.completed = len(job.data)

        # All URLs processed
        job_store.update_job(
            job_id,
            status=JobStatus.completed,
            total=len(req.urls),
            completed=len(req.urls),
        )
        logger.info("Batch job %s completed with %d URLs", job_id, len(req.urls))

    except asyncio.CancelledError:
        logger.info("Batch job %s task cancelled", job_id)
        raise

    except Exception:
        logger.exception("Unexpected error in batch scrape job %s", job_id)
        job_store.update_job(
            job_id,
            status=JobStatus.failed,
            error="Internal error during batch scrape",
        )


@router.post("/batch/scrape")
async def batch_scrape_create(
    req: BatchScrapeRequest,
    request: Request,
    scrape_service: ScrapeService = Depends(get_scrape_service),
    _api_key: str | None = Depends(get_api_key),
) -> BatchScrapeCreateResponse | ErrorResponse:
    """Start an async batch scrape job and return its ID."""
    job_store = _get_job_store(request)

    try:
        job = job_store.create_job(total=len(req.urls))
    except MaxJobsExceededError as exc:
        return ErrorResponse(error=str(exc))

    task = asyncio.create_task(_run_batch_scrape(job.id, job_store, scrape_service, req))
    job_store.set_task(job.id, task)

    return BatchScrapeCreateResponse(id=job.id)


@router.get("/batch/scrape/{job_id}")
async def batch_scrape_status(
    job_id: str,
    request: Request,
    offset: int = 0,
    _api_key: str | None = Depends(get_api_key),
) -> BatchScrapeStatusResponse | ErrorResponse:
    """Return the status of a batch scrape job with paginated data."""
    job_store = _get_job_store(request)
    base_url = str(request.url).split("?")[0]
    result = job_store.get_job(job_id, offset=offset, base_url=base_url)

    if result is None:
        return ErrorResponse(error=f"Job {job_id} not found")

    return BatchScrapeStatusResponse(
        status=result["status"],
        total=result["total"],
        completed=result["completed"],
        data=result["data"],
        next=result["next"],
        error=result["error"],
    )
