"""API routes for redesign_service."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.schemas import (
    AccessibilityCategoryResponse,
    AccessibilityFindingResponse,
    AccessibilityScoreResponse,
    AsyncJobResponse,
    BatchJobResponse,
    BatchListItem,
    BatchListResponse,
    BatchPageErrorInfo,
    BatchPageJobInfo,
    BatchPageStatusInfo,
    BatchRedesignRequest,
    BatchResultsResponse,
    BatchRetryResponse,
    BatchStatusResponse,
    CancelJobResponse,
    CreateCustomStyleRequest,
    CustomStyleResponse,
    IterationHistoryResponse,
    IterationSummary,
    JobListItem,
    JobListResponse,
    JobStatusResponse,
    RedesignRequest,
    RedesignResultResponse,
    RefineRequest,
    StyleListResponse,
    StylePreviewRequest,
    StylePreviewResponse,
    UpdateCustomStyleRequest,
    VariantComparisonResponse,
    VariantResult,
    WebhookDeliveryStatus,
)
from src.database.session import get_db
from src.services.job_manager import JobManager
from src.services.redesign_service import RedesignService
from src.services.storage_service import StorageService
from src.services.style_manager import StyleManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/redesign", tags=["redesign"])


def _get_tenant_id(request: Request) -> str:
    return getattr(request.state, "tenant_id", "anonymous")


def _get_redesign_service(request: Request) -> RedesignService:
    return request.app.state.redesign_service


def _get_storage(request: Request) -> StorageService:
    return request.app.state.storage_service


def _get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


def _get_cache_service(request: Request):
    """Return the CacheService if available, or None."""
    return getattr(request.app.state, "cache_service", None)


# ============================================================================
# Redesign Endpoints
# ============================================================================


@router.post("")
async def create_redesign(
    body: RedesignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AsyncJobResponse:
    """Create a new redesign job (always async)."""
    tenant_id = _get_tenant_id(request)
    service = _get_redesign_service(request)

    job_id = await service.create_job(
        db,
        tenant_id=tenant_id,
        url=body.url,
        html_content=body.html_content,
        scope=body.scope,
        style=body.style,
        page_type=body.page_type,
        critique_findings=[f.model_dump() for f in body.critique_findings]
        if body.critique_findings
        else None,
        brand_info=body.brand.model_dump() if body.brand else None,
        site_analysis=body.site_analysis.model_dump() if body.site_analysis else None,
        user_context=body.user_context.model_dump(exclude_none=True) if body.user_context else None,
        styles=body.styles,
        component_target=body.component_target.model_dump() if body.component_target else None,
        webhook_url=body.webhook_url,
        webhook_secret=body.webhook_secret,
    )
    await db.commit()

    # Process job in background with independent session
    session_factory = _get_session_factory(request)
    asyncio.create_task(
        _process_job_background(
            service,
            session_factory,
            job_id,
            tenant_id,
            run_accessibility_check=body.run_accessibility_check,
            auto_fix_accessibility=body.auto_fix_accessibility,
            accessibility_threshold=body.accessibility_threshold,
            generate_screenshots=body.generate_screenshots,
            generate_concept_images=body.generate_concept_images,
        )
    )

    return AsyncJobResponse(
        job_id=job_id,
        status="pending",
        poll_url=f"/api/v1/redesign/jobs/{job_id}",
        webhook_configured=body.webhook_url is not None,
    )


async def _process_job_background(
    service: RedesignService,
    session_factory: async_sessionmaker[AsyncSession],
    job_id: str,
    tenant_id: str,
    **kwargs: object,
) -> None:
    """Background task to process a redesign job with an independent session."""
    try:
        async with session_factory() as db:
            await service.process_job(db, job_id, tenant_id, **kwargs)
    except Exception:
        logger.exception("Background redesign job %s failed", job_id)


# ============================================================================
# Job Status Endpoints
# ============================================================================


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JobStatusResponse:
    """Get status of a redesign job."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    result_url = f"/api/v1/redesign/jobs/{job_id}/result" if job.status == "completed" else None
    refine_url = f"/api/v1/redesign/jobs/{job_id}/refine" if job.status == "completed" else None

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        url=job.url,
        scope=job.scope,
        style=job.style,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error=job.error_message,
        result_url=result_url,
        iteration_number=job.iteration_number,
        parent_job_id=job.parent_job_id,
        root_job_id=job.root_job_id,
        refine_url=refine_url,
        accessibility_score=job.accessibility_score,
        batch_id=job.batch_id,
    )


@router.get("/jobs/{job_id}/result")
async def get_job_result(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedesignResultResponse:
    """Get the full result of a completed redesign job."""
    # Check Redis cache first for non-variant results
    cache_svc = _get_cache_service(request)
    if cache_svc is not None:
        cached = await cache_svc.get_cached_job_result(job_id)
        if cached is not None:
            # Build accessibility response from cached data
            a11y = None
            cached_a11y_report = cached.get("accessibility_report")
            if cached_a11y_report:
                a11y = AccessibilityScoreResponse(
                    overall_score=cached_a11y_report.get("overall_score", 0),
                    categories=[
                        AccessibilityCategoryResponse(
                            category=c.get("category", ""),
                            score=c.get("score", 0),
                            findings=[
                                AccessibilityFindingResponse(**f) for f in c.get("findings", [])
                            ],
                        )
                        for c in cached_a11y_report.get("categories", [])
                    ],
                    findings=[
                        AccessibilityFindingResponse(**f)
                        for f in cached_a11y_report.get("findings", [])
                    ],
                    html_was_fixed=cached_a11y_report.get("html_was_fixed", False),
                )

            return RedesignResultResponse(
                job_id=job_id,
                url=cached.get("url", ""),
                scope=cached.get("scope", "full_page"),
                style=cached.get("style", "modern"),
                redesigned_html_path=cached.get("redesigned_html_path"),
                section_html_paths=cached.get("section_html_paths"),
                screenshots=cached.get("screenshot_paths"),
                concept_image_paths=cached.get("concept_image_paths"),
                component_html_path=cached.get("component_html_path"),
                accessibility=a11y,
                original_screenshots=cached.get("original_screenshot_paths"),
                comparisons=cached.get("comparison_paths"),
                diffs=cached.get("diff_paths"),
                html_validation=cached.get("html_validation_report"),
            )

    # Cache miss -- fall back to PostgreSQL
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed (status: {job.status})")

    # Build variant results if present
    variants = None
    if job.styles and len(job.styles) > 1:
        variant_records = await JobManager.get_variants(db, job_id)
        variants = [
            VariantResult(
                variant_id=v.variant_id,
                style=v.style,
                status=v.status,
                redesigned_html_path=v.redesigned_html_path,
                screenshot_paths=v.screenshot_paths,
                error=v.error_message,
            )
            for v in variant_records
        ]

    # Build accessibility response
    a11y = None
    if job.accessibility_report:
        report = job.accessibility_report
        a11y = AccessibilityScoreResponse(
            overall_score=report.get("overall_score", 0),
            categories=[
                AccessibilityCategoryResponse(
                    category=c.get("category", ""),
                    score=c.get("score", 0),
                    findings=[AccessibilityFindingResponse(**f) for f in c.get("findings", [])],
                )
                for c in report.get("categories", [])
            ],
            findings=[AccessibilityFindingResponse(**f) for f in report.get("findings", [])],
            html_was_fixed=report.get("html_was_fixed", False),
        )

    return RedesignResultResponse(
        job_id=job.job_id,
        url=job.url,
        scope=job.scope,
        style=job.style,
        redesigned_html_path=job.redesigned_html_path,
        section_html_paths=job.section_html_paths,
        screenshots=job.screenshot_paths,
        concept_image_paths=job.concept_image_paths,
        variants=variants,
        component_html_path=job.component_html_path,
        accessibility=a11y,
        original_screenshots=job.original_screenshot_paths,
        comparisons=job.comparison_paths,
        diffs=job.diff_paths,
        html_validation=job.html_validation_report,
    )


@router.get("/jobs/{job_id}/html")
async def download_html(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the redesigned HTML for a completed job."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed (status: {job.status})")
    if not job.redesigned_html_path:
        raise HTTPException(status_code=404, detail="Redesigned HTML not found")

    storage = _get_storage(request)
    html_data = await storage.retrieve_text(job.redesigned_html_path)
    if html_data is None:
        raise HTTPException(status_code=404, detail="HTML file not found on storage")

    return Response(
        content=html_data,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="redesign_{job_id}.html"',
        },
    )


@router.get("/jobs/{job_id}/screenshots/{viewport}")
async def download_screenshot(
    job_id: str,
    viewport: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download a screenshot for a specific viewport."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed (status: {job.status})")
    if not job.screenshot_paths or viewport not in job.screenshot_paths:
        raise HTTPException(
            status_code=404, detail=f"Screenshot not found for viewport: {viewport}"
        )

    storage = _get_storage(request)
    image_data = await storage.retrieve(job.screenshot_paths[viewport])
    if image_data is None:
        raise HTTPException(status_code=404, detail="Screenshot file not found on storage")

    return Response(
        content=image_data,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="redesign_{job_id}_{viewport}.png"',
        },
    )


# ============================================================================
# Feature 4: Variant Comparison
# ============================================================================


@router.get("/jobs/{job_id}/compare")
async def compare_variants(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> VariantComparisonResponse:
    """Compare all style variants for a job."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    variants = await JobManager.get_variants(db, job_id)
    if not variants:
        raise HTTPException(status_code=404, detail="No variants found for this job")

    return VariantComparisonResponse(
        job_id=job_id,
        variants=[
            VariantResult(
                variant_id=v.variant_id,
                style=v.style,
                status=v.status,
                redesigned_html_path=v.redesigned_html_path,
                screenshot_paths=v.screenshot_paths,
                error=v.error_message,
            )
            for v in variants
        ],
    )


@router.get("/jobs/{job_id}/variants/{style}/html")
async def download_variant_html(
    job_id: str,
    style: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the HTML for a specific variant."""
    variants = await JobManager.get_variants(db, job_id)
    variant = next((v for v in variants if v.style == style), None)
    if variant is None:
        raise HTTPException(status_code=404, detail=f"Variant not found: {style}")
    if variant.status != "completed" or not variant.redesigned_html_path:
        raise HTTPException(
            status_code=409, detail=f"Variant not completed (status: {variant.status})"
        )

    storage = _get_storage(request)
    html_data = await storage.retrieve_text(variant.redesigned_html_path)
    if html_data is None:
        raise HTTPException(status_code=404, detail="Variant HTML file not found")

    return Response(
        content=html_data,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="variant_{job_id}_{style}.html"',
        },
    )


# ============================================================================
# Feature 5: Iteration/Refinement
# ============================================================================


@router.post("/jobs/{job_id}/refine")
async def refine_redesign(
    job_id: str,
    body: RefineRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AsyncJobResponse:
    """Refine an existing redesign with feedback."""
    tenant_id = _get_tenant_id(request)
    service = _get_redesign_service(request)

    try:
        new_job_id = await service.create_refinement_job(
            db,
            parent_job_id=job_id,
            feedback=body.feedback,
            generate_screenshots=body.generate_screenshots,
            generate_concept_images=body.generate_concept_images,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()

    session_factory = _get_session_factory(request)
    asyncio.create_task(
        _process_refinement_background(
            service,
            session_factory,
            new_job_id,
            tenant_id,
            generate_screenshots=body.generate_screenshots,
            generate_concept_images=body.generate_concept_images,
            focus_areas=body.focus_areas,
        )
    )

    return AsyncJobResponse(
        job_id=new_job_id,
        status="pending",
        poll_url=f"/api/v1/redesign/jobs/{new_job_id}",
    )


async def _process_refinement_background(
    service: RedesignService,
    session_factory: async_sessionmaker[AsyncSession],
    job_id: str,
    tenant_id: str,
    **kwargs: object,
) -> None:
    try:
        async with session_factory() as db:
            await service.process_refinement_job(db, job_id, tenant_id, **kwargs)
    except Exception:
        logger.exception("Background refinement job %s failed", job_id)


@router.get("/jobs/{job_id}/history")
async def get_iteration_history(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> IterationHistoryResponse:
    """Get the full iteration history for a job."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    root_id = job.root_job_id or job.job_id
    history = await JobManager.get_iteration_history(db, root_id)

    return IterationHistoryResponse(
        root_job_id=root_id,
        iterations=[
            IterationSummary(
                job_id=j.job_id,
                iteration_number=j.iteration_number or 0,
                status=j.status,
                feedback=j.feedback_text,
                created_at=j.created_at.isoformat() if j.created_at else None,
            )
            for j in history
        ],
        total_iterations=len(history),
    )


# ============================================================================
# Feature 6: Component HTML Download
# ============================================================================


@router.get("/jobs/{job_id}/component-html")
async def download_component_html(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the redesigned component HTML."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed (status: {job.status})")
    if not job.component_html_path:
        raise HTTPException(status_code=404, detail="Component HTML not found")

    storage = _get_storage(request)
    html_data = await storage.retrieve_text(job.component_html_path)
    if html_data is None:
        raise HTTPException(status_code=404, detail="Component HTML file not found on storage")

    return Response(
        content=html_data,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="component_{job_id}.html"',
        },
    )


# ============================================================================
# Feature 8: Visual Comparison Downloads
# ============================================================================


@router.get("/jobs/{job_id}/original/{viewport}")
async def download_original_screenshot(
    job_id: str,
    viewport: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download original screenshot for a viewport."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if not job.original_screenshot_paths or viewport not in job.original_screenshot_paths:
        raise HTTPException(
            status_code=404, detail=f"Original screenshot not found for viewport: {viewport}"
        )

    storage = _get_storage(request)
    data = await storage.retrieve(job.original_screenshot_paths[viewport])
    if data is None:
        raise HTTPException(status_code=404, detail="Original screenshot file not found")

    return Response(content=data, media_type="image/png")


@router.get("/jobs/{job_id}/comparison/{viewport}")
async def download_comparison(
    job_id: str,
    viewport: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download side-by-side comparison for a viewport."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if not job.comparison_paths or viewport not in job.comparison_paths:
        raise HTTPException(
            status_code=404, detail=f"Comparison not found for viewport: {viewport}"
        )

    storage = _get_storage(request)
    data = await storage.retrieve(job.comparison_paths[viewport])
    if data is None:
        raise HTTPException(status_code=404, detail="Comparison file not found")

    return Response(content=data, media_type="image/png")


@router.get("/jobs/{job_id}/diff/{viewport}")
async def download_diff(
    job_id: str,
    viewport: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download pixel diff for a viewport."""
    job = await JobManager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if not job.diff_paths or viewport not in job.diff_paths:
        raise HTTPException(status_code=404, detail=f"Diff not found for viewport: {viewport}")

    storage = _get_storage(request)
    data = await storage.retrieve(job.diff_paths[viewport])
    if data is None:
        raise HTTPException(status_code=404, detail="Diff file not found")

    return Response(content=data, media_type="image/png")


# ============================================================================
# Feature 9: Webhook Delivery Status
# ============================================================================


@router.get("/jobs/{job_id}/webhooks")
async def get_webhook_deliveries(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryStatus]:
    """Get webhook delivery log for a job."""
    from sqlalchemy import select

    from src.database.models import WebhookDeliveryLog

    result = await db.execute(
        select(WebhookDeliveryLog)
        .where(WebhookDeliveryLog.job_id == job_id)
        .order_by(WebhookDeliveryLog.created_at.desc())
    )
    logs = result.scalars().all()

    return [
        WebhookDeliveryStatus(
            attempt_number=log.attempt_number,
            event_type=log.event_type,
            status=log.status,
            response_status=log.response_status,
            created_at=log.created_at.isoformat() if log.created_at else None,
        )
        for log in logs
    ]


# ============================================================================
# Feature 3: Custom Style CRUD
# ============================================================================


@router.get("/styles")
async def list_styles(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StyleListResponse:
    """List all custom styles for the tenant."""
    tenant_id = _get_tenant_id(request)
    styles = await StyleManager.list_styles(db, tenant_id)
    return StyleListResponse(
        styles=[
            CustomStyleResponse(
                style_id=s.style_id,
                name=s.name,
                slug=s.slug,
                description=s.description,
                color_palette=s.color_palette,
                typography=s.typography,
                layout=s.layout,
                example_references=s.example_references,
                is_active=s.is_active,
                created_at=s.created_at.isoformat() if s.created_at else None,
            )
            for s in styles
        ],
        count=len(styles),
    )


@router.post("/styles")
async def create_style(
    body: CreateCustomStyleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CustomStyleResponse:
    """Create a new custom style."""
    tenant_id = _get_tenant_id(request)

    # Enforce max styles per tenant
    from src.config import get_settings as _get_settings

    max_styles = _get_settings().redesign.max_custom_styles_per_tenant
    current_count = await StyleManager.count_styles(db, tenant_id)
    if current_count >= max_styles:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum custom styles ({max_styles}) reached for this tenant",
        )

    style = await StyleManager.create_style(
        db,
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        color_palette=body.color_palette.model_dump(exclude_none=True)
        if body.color_palette
        else None,
        typography=body.typography.model_dump(exclude_none=True) if body.typography else None,
        layout=body.layout.model_dump(exclude_none=True) if body.layout else None,
        example_references=body.example_references,
    )
    await db.commit()
    return CustomStyleResponse(
        style_id=style.style_id,
        name=style.name,
        slug=style.slug,
        description=style.description,
        color_palette=style.color_palette,
        typography=style.typography,
        layout=style.layout,
        example_references=style.example_references,
        is_active=style.is_active,
        created_at=style.created_at.isoformat() if style.created_at else None,
    )


@router.get("/styles/{style_id}")
async def get_style(
    style_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CustomStyleResponse:
    """Get a custom style by ID."""
    style = await StyleManager.get_style(db, style_id)
    if style is None:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")
    return CustomStyleResponse(
        style_id=style.style_id,
        name=style.name,
        slug=style.slug,
        description=style.description,
        color_palette=style.color_palette,
        typography=style.typography,
        layout=style.layout,
        example_references=style.example_references,
        is_active=style.is_active,
        created_at=style.created_at.isoformat() if style.created_at else None,
    )


@router.put("/styles/{style_id}")
async def update_style(
    style_id: str,
    body: UpdateCustomStyleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CustomStyleResponse:
    """Update a custom style."""
    existing = await StyleManager.get_style(db, style_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")

    update_data = body.model_dump(exclude_none=True)
    if "color_palette" in update_data and body.color_palette:
        update_data["color_palette"] = body.color_palette.model_dump(exclude_none=True)
    if "typography" in update_data and body.typography:
        update_data["typography"] = body.typography.model_dump(exclude_none=True)
    if "layout" in update_data and body.layout:
        update_data["layout"] = body.layout.model_dump(exclude_none=True)

    await StyleManager.update_style(db, style_id, **update_data)
    await db.commit()

    # Invalidate cached style description
    cache_service = getattr(request.app.state, "cache_service", None)
    if cache_service:
        await cache_service.invalidate_style(style_id)

    updated = await StyleManager.get_style(db, style_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Style not found after update")
    return CustomStyleResponse(
        style_id=updated.style_id,
        name=updated.name,
        slug=updated.slug,
        description=updated.description,
        color_palette=updated.color_palette,
        typography=updated.typography,
        layout=updated.layout,
        example_references=updated.example_references,
        is_active=updated.is_active,
        created_at=updated.created_at.isoformat() if updated.created_at else None,
    )


@router.delete("/styles/{style_id}")
async def delete_style(
    style_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a custom style."""
    deleted = await StyleManager.delete_style(db, style_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")
    await db.commit()

    # Invalidate cached style description
    cache_service = getattr(request.app.state, "cache_service", None)
    if cache_service:
        await cache_service.invalidate_style(style_id)

    return {"deleted": True, "style_id": style_id}


# ============================================================================
# Feature 10: Batch Processing
# ============================================================================


@router.post("/batch")
async def create_batch(
    body: BatchRedesignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BatchJobResponse:
    """Create a batch redesign job for multiple pages."""
    tenant_id = _get_tenant_id(request)
    service = _get_redesign_service(request)

    pages = [
        {
            "url": p.url,
            "page_type": p.page_type,
            "html_content": p.html_content,
        }
        for p in body.pages
    ]

    batch_id, page_jobs = await service.create_batch(
        db,
        tenant_id=tenant_id,
        pages=pages,
        style=body.style,
        scope=body.scope,
        generate_screenshots=body.generate_screenshots,
        generate_concept_images=body.generate_concept_images,
        critique_findings=[f.model_dump() for f in body.critique_findings]
        if body.critique_findings
        else None,
        brand_info=body.brand.model_dump() if body.brand else None,
        site_analysis=body.site_analysis.model_dump() if body.site_analysis else None,
        user_context=body.user_context.model_dump(exclude_none=True) if body.user_context else None,
        webhook_url=body.webhook_url,
        webhook_secret=body.webhook_secret,
    )
    await db.commit()

    session_factory = _get_session_factory(request)
    asyncio.create_task(_process_batch_background(service, session_factory, batch_id, tenant_id))

    return BatchJobResponse(
        batch_id=batch_id,
        status="pending",
        total_pages=len(page_jobs),
        page_jobs=[
            BatchPageJobInfo(
                job_id=pj["job_id"],
                url=pj["url"],
                page_type=pj.get("page_type"),
                priority_score=pj.get("priority_score"),
            )
            for pj in page_jobs
        ],
        poll_url=f"/api/v1/redesign/batch/{batch_id}",
    )


async def _process_batch_background(
    service: RedesignService,
    session_factory: async_sessionmaker[AsyncSession],
    batch_id: str,
    tenant_id: str,
) -> None:
    try:
        await service.process_batch(session_factory, batch_id, tenant_id)
    except Exception:
        logger.exception("Background batch %s failed", batch_id)


@router.get("/batch/{batch_id}")
async def get_batch_status(
    batch_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BatchStatusResponse:
    """Get status of a batch job."""
    from src.services.batch_manager import BatchManager

    batch = await BatchManager.get_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

    jobs = await BatchManager.get_batch_jobs(db, batch_id)

    return BatchStatusResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        total_pages=batch.total_pages,
        completed_pages=batch.completed_pages,
        failed_pages=batch.failed_pages,
        page_statuses=[
            BatchPageStatusInfo(
                job_id=j.job_id,
                url=j.url,
                status=j.status,
                error=j.error_message,
            )
            for j in jobs
        ],
    )


@router.get("/batch/{batch_id}/results")
async def get_batch_results(
    batch_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BatchResultsResponse:
    """Get results of a completed batch job."""
    from src.services.batch_manager import BatchManager

    batch = await BatchManager.get_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

    jobs = await BatchManager.get_batch_jobs(db, batch_id)

    results = []
    errors = []
    for j in jobs:
        if j.status == "completed":
            results.append(
                RedesignResultResponse(
                    job_id=j.job_id,
                    url=j.url,
                    scope=j.scope,
                    style=j.style,
                    redesigned_html_path=j.redesigned_html_path,
                    section_html_paths=j.section_html_paths,
                    screenshots=j.screenshot_paths,
                    concept_image_paths=j.concept_image_paths,
                )
            )
        elif j.status == "failed":
            errors.append(
                BatchPageErrorInfo(
                    job_id=j.job_id,
                    url=j.url,
                    error=j.error_message or "Unknown error",
                )
            )

    return BatchResultsResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        total_pages=batch.total_pages,
        completed_pages=batch.completed_pages,
        failed_pages=batch.failed_pages,
        results=results,
        errors=errors,
    )


# ============================================================================
# Enhancement 2: Job Cancellation & Listing
# ============================================================================


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CancelJobResponse:
    """Cancel a pending or processing job."""
    cancelled = await JobManager.cancel_job(db, job_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} cannot be cancelled (not found or already finished)",
        )
    await db.commit()

    job = await JobManager.get_job(db, job_id)
    return CancelJobResponse(
        job_id=job_id,
        status="cancelled",
        cancelled_at=job.cancelled_at.isoformat() if job and job.cancelled_at else "",
    )


@router.get("/jobs")
async def list_jobs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None, description="Filter by status"),
    page_type: str | None = Query(default=None, description="Filter by page type"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> JobListResponse:
    """List jobs for the current tenant with optional filters."""
    tenant_id = _get_tenant_id(request)
    jobs, total = await JobManager.list_jobs(
        db,
        tenant_id,
        status=status,
        page_type=page_type,
        limit=limit,
        offset=offset,
    )
    return JobListResponse(
        jobs=[
            JobListItem(
                job_id=j.job_id,
                url=j.url,
                status=j.status,
                scope=j.scope,
                style=j.style,
                page_type=j.page_type,
                created_at=j.created_at.isoformat() if j.created_at else None,
                completed_at=j.completed_at.isoformat() if j.completed_at else None,
            )
            for j in jobs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Enhancement 7: Style Preview
# ============================================================================


@router.post("/styles/{style_id}/preview")
async def preview_style(
    style_id: str,
    body: StylePreviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StylePreviewResponse:
    """Preview a custom style applied to an HTML snippet."""
    style = await StyleManager.get_style(db, style_id)
    if style is None:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")

    style_desc = StyleManager.resolve_style_description(style)
    service = _get_redesign_service(request)

    # Use a lightweight LLM call to apply the style
    prompt = (
        f"Apply the following design style to this HTML snippet.\n\n"
        f"## Style\n{style_desc}\n\n"
        f"## HTML Snippet\n```html\n{body.html_snippet}\n```\n\n"
        f"Output ONLY the styled HTML using Tailwind CSS classes in a ```html code block."
    )
    llm_result = await service._html_gen._call_claude(prompt, temperature=0.4)

    from src.services.html_generator import _extract_html_block

    styled_html = _extract_html_block(llm_result.text)

    return StylePreviewResponse(
        styled_html=styled_html,
        style_description=style_desc,
    )


# ============================================================================
# Enhancement 11: Batch Enhancements
# ============================================================================


@router.get("/batch")
async def list_batches(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BatchListResponse:
    """List all batches for the current tenant."""
    from src.services.batch_manager import BatchManager

    tenant_id = _get_tenant_id(request)
    batches = await BatchManager.list_batches(db, tenant_id)
    return BatchListResponse(
        batches=[
            BatchListItem(
                batch_id=b.batch_id,
                status=b.status,
                total_pages=b.total_pages,
                completed_pages=b.completed_pages,
                failed_pages=b.failed_pages,
                created_at=b.created_at.isoformat() if b.created_at else None,
            )
            for b in batches
        ],
        total=len(batches),
    )


@router.post("/batch/{batch_id}/cancel")
async def cancel_batch(
    batch_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel a batch and all its pending child jobs."""
    from src.services.batch_manager import BatchManager

    cancelled = await BatchManager.cancel_batch(db, batch_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Batch {batch_id} cannot be cancelled (not found or already finished)",
        )
    await db.commit()
    return {"cancelled": True, "batch_id": batch_id}


@router.post("/batch/{batch_id}/retry-failed")
async def retry_failed_batch_pages(
    batch_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BatchRetryResponse:
    """Re-queue failed pages in a batch for retry."""
    from src.services.batch_manager import BatchManager

    batch = await BatchManager.get_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

    failed_jobs = await BatchManager.get_failed_jobs(db, batch_id)
    if not failed_jobs:
        raise HTTPException(status_code=409, detail="No failed jobs to retry")

    retried_ids: list[str] = []
    for job in failed_jobs:
        await BatchManager.reset_job_for_retry(db, job.job_id)
        retried_ids.append(job.job_id)

    # Update batch counters
    from sqlalchemy import update as sa_update

    from src.database.models import BatchJob as BatchJobModel

    await db.execute(
        sa_update(BatchJobModel)
        .where(BatchJobModel.batch_id == batch_id)
        .values(
            failed_pages=batch.failed_pages - len(retried_ids),
            status="processing",
        )
    )
    await db.commit()

    # Re-launch processing in background
    tenant_id = _get_tenant_id(request)
    service = _get_redesign_service(request)
    session_factory = _get_session_factory(request)
    asyncio.create_task(_process_batch_background(service, session_factory, batch_id, tenant_id))

    return BatchRetryResponse(
        batch_id=batch_id,
        retried_jobs=retried_ids,
        count=len(retried_ids),
    )
