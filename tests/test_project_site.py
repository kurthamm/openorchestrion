from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
WHITEPAPER = REPO_ROOT / "docs" / "whitepaper" / "OpenOrchestrion_White_Paper_v2.md"
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pages.yml"


def test_project_site_is_static_and_self_contained() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    css = (SITE / "site.css").read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="site.css">' in html
    assert "<script" not in html.casefold()
    assert "@import" not in css
    assert "fonts.googleapis" not in html + css
    assert "cdn" not in html.casefold()
    assert "analytics" not in html.casefold()


def test_project_site_distinguishes_recorded_and_pending_hardware_evidence() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")

    assert "WK-220 evidence recorded" in html
    assert "120-minute headless" in html
    assert "acoustic synchronization is not yet measured" in html
    assert "owner-deferred" in html


def test_project_site_links_to_living_repository_docs() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    required = (
        "docs/appliance-install.md",
        "docs/whitepaper/OpenOrchestrion_White_Paper_v2.md",
        "PROJECT_STATUS.md",
        "ROADMAP.md",
    )
    for target in required:
        assert target in html


def test_pages_workflow_publishes_only_the_static_site_from_main() -> None:
    source = PAGES_WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(source)

    # PyYAML follows YAML 1.1 and may parse the key `on` as boolean True.
    triggers = data.get("on", data.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in triggers
    assert data["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    deploy = data["jobs"]["deploy"]
    assert deploy["environment"]["name"] == "github-pages"
    workflow_text = PAGES_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"path:\s*site\b", workflow_text)
    assert "actions/deploy-pages@" in workflow_text


def test_v2_whitepaper_is_truthful_about_software_vs_hardware_evidence() -> None:
    paper = WHITEPAPER.read_text(encoding="utf-8")

    assert "White Paper v2.1" in paper
    assert "Implemented software" in paper
    assert "Hardware evidence pending" in paper
    assert "passing 120-minute loaded headless" in paper
    assert "does not claim measured latency" in paper


def test_public_status_no_longer_calls_the_project_repository_bootstrap() -> None:
    status = (REPO_ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    assert "architecture / hardware validation / repository bootstrap" not in status
    assert "OpenAI Responses API adapter" in status
    assert "rendering controls for the next queue" in status
    assert "verified backup/restore" in status
