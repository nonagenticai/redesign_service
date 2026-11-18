"""Custom style definition management with CRUD and LLM prompt composition."""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CustomStyle

logger = logging.getLogger(__name__)


def slugify(name: str) -> str:
    """Convert a style name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


class StyleManager:
    """CRUD operations for custom style definitions."""

    @staticmethod
    async def create_style(
        db: AsyncSession,
        *,
        tenant_id: str,
        name: str,
        description: str | None = None,
        color_palette: dict | None = None,
        typography: dict | None = None,
        layout: dict | None = None,
        example_references: list[str] | None = None,
    ) -> CustomStyle:
        style = CustomStyle(
            style_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=name,
            slug=slugify(name),
            description=description,
            color_palette=color_palette,
            typography=typography,
            layout=layout,
            example_references=example_references,
            is_active=True,
        )
        db.add(style)
        await db.flush()
        logger.info(
            "Created custom style '%s' (id=%s) for tenant %s", name, style.style_id, tenant_id
        )
        return style

    @staticmethod
    async def get_style(db: AsyncSession, style_id: str) -> CustomStyle | None:
        result = await db.execute(select(CustomStyle).where(CustomStyle.style_id == style_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_style_by_slug(db: AsyncSession, tenant_id: str, slug: str) -> CustomStyle | None:
        result = await db.execute(
            select(CustomStyle).where(
                CustomStyle.tenant_id == tenant_id,
                CustomStyle.slug == slug,
                CustomStyle.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_styles(db: AsyncSession, tenant_id: str) -> list[CustomStyle]:
        result = await db.execute(
            select(CustomStyle)
            .where(CustomStyle.tenant_id == tenant_id, CustomStyle.is_active.is_(True))
            .order_by(CustomStyle.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_style(
        db: AsyncSession,
        style_id: str,
        **kwargs: object,
    ) -> bool:
        allowed = {
            "name",
            "description",
            "color_palette",
            "typography",
            "layout",
            "example_references",
            "is_active",
        }
        values = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if "name" in values:
            values["slug"] = slugify(str(values["name"]))
        if not values:
            return False
        result = await db.execute(
            update(CustomStyle).where(CustomStyle.style_id == style_id).values(**values)
        )
        return result.rowcount > 0  # type: ignore[union-attr]

    @staticmethod
    async def count_styles(db: AsyncSession, tenant_id: str) -> int:
        """Count active styles for a tenant."""
        result = await db.execute(
            select(sa_func.count())
            .select_from(CustomStyle)
            .where(CustomStyle.tenant_id == tenant_id, CustomStyle.is_active.is_(True))
        )
        return result.scalar() or 0

    @staticmethod
    async def delete_style(db: AsyncSession, style_id: str) -> bool:
        result = await db.execute(delete(CustomStyle).where(CustomStyle.style_id == style_id))
        return result.rowcount > 0  # type: ignore[union-attr]

    @staticmethod
    def resolve_style_description(style: CustomStyle) -> str:
        """Compose a rich LLM prompt description from custom style fields."""
        parts: list[str] = []
        if style.description:
            parts.append(style.description)

        if style.color_palette:
            cp = style.color_palette
            colors = []
            if cp.get("primary"):
                colors.append(f"primary={cp['primary']}")
            if cp.get("secondary"):
                colors.append(f"secondary={cp['secondary']}")
            if cp.get("accent"):
                colors.append(f"accent={cp['accent']}")
            if cp.get("background"):
                colors.append(f"background={cp['background']}")
            if cp.get("text"):
                colors.append(f"text={cp['text']}")
            if colors:
                parts.append(f"Color palette: {', '.join(colors)}.")

        if style.typography:
            tp = style.typography
            typo_parts = []
            if tp.get("heading_font"):
                typo_parts.append(f"headings in {tp['heading_font']}")
            if tp.get("body_font"):
                typo_parts.append(f"body text in {tp['body_font']}")
            if tp.get("scale"):
                typo_parts.append(f"{tp['scale']} type scale")
            if typo_parts:
                parts.append(f"Typography: {', '.join(typo_parts)}.")

        if style.layout:
            lp = style.layout
            layout_parts = []
            if lp.get("max_width"):
                layout_parts.append(f"max width {lp['max_width']}")
            if lp.get("spacing"):
                layout_parts.append(f"{lp['spacing']} spacing")
            if lp.get("grid_columns"):
                layout_parts.append(f"{lp['grid_columns']}-column grid")
            if lp.get("border_radius"):
                layout_parts.append(f"{lp['border_radius']} border radius")
            if layout_parts:
                parts.append(f"Layout: {', '.join(layout_parts)}.")

        if style.example_references:
            refs = ", ".join(str(r) for r in style.example_references[:3])
            parts.append(f"Reference sites for inspiration: {refs}.")

        return " ".join(parts) if parts else f"Custom style: {style.name}"
