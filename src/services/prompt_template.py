"""Jinja2-based prompt template loader for LLM prompts."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "redesign"


class PromptTemplateLoader:
    """Loads and renders Jinja2 prompt templates with version-aware search paths."""

    def __init__(
        self,
        version: str = "v1",
        template_dir: str | None = None,
    ) -> None:
        self._version = version
        base_dir = Path(template_dir) if template_dir else _DEFAULT_TEMPLATE_DIR
        version_dir = base_dir / version

        search_paths: list[str] = []
        if version_dir.is_dir():
            search_paths.append(str(version_dir))
        if base_dir.is_dir():
            search_paths.append(str(base_dir))

        if search_paths:
            # nosec B701 - autoescape stays off deliberately. These templates are
            # LLM prompts (src/templates/redesign/**/*.md.j2) rendered to a string
            # and passed as chat message content (see html_generator: role=system
            # / role=user), never emitted as HTML to a browser. full_page.md.j2
            # takes html_excerpt as a template VARIABLE, so autoescape=True would
            # escape the very markup the model is meant to read.
            self._env = Environment(  # nosec B701
                loader=FileSystemLoader(search_paths),
                autoescape=False,  # nosec B701
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            self._available = True
        else:
            self._env = None
            self._available = False
            logger.warning("No template directories found at %s", base_dir)

    @property
    def version(self) -> str:
        return self._version

    def render(self, template_name: str, **kwargs: object) -> str | None:
        """Render a template with the given context. Returns None if template not found."""
        if not self._available or self._env is None:
            return None
        try:
            template = self._env.get_template(template_name)
            return template.render(**kwargs)
        except TemplateNotFound:
            logger.debug("Template not found: %s", template_name)
            return None

    def render_or_fallback(self, template_name: str, fallback: str, **kwargs: object) -> str:
        """Render a template, falling back to the provided string if template not found."""
        result = self.render(template_name, **kwargs)
        if result is not None:
            return result
        return fallback

    def has_template(self, template_name: str) -> bool:
        """Check if a template exists."""
        if not self._available or self._env is None:
            return False
        try:
            self._env.get_template(template_name)
            return True
        except TemplateNotFound:
            return False

    def list_templates(self) -> list[str]:
        """List all available templates."""
        if not self._available or self._env is None:
            return []
        return self._env.list_templates()
