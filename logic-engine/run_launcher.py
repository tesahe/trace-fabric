import asyncio
from pathlib import Path


ROOT = Path("/Users/tesahe/Desktop/Endeavors/trace-fabric")
SCRAPER_DIR = ROOT / "scraper-engine"


async def launch_discovery_run(
    *,
    run_id: str,
    industry: str,
    location: str,
    limit: int,
    max_pages: int,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "cargo",
        "run",
        "--",
        "discover",
        "--industry",
        industry,
        "--location",
        location,
        "--limit",
        str(limit),
        "--max-pages",
        str(max_pages),
        "--run-id",
        run_id,
        cwd=str(SCRAPER_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def launch_url_run(
    *,
    run_id: str,
    website: str,
    industry: str | None = None,
    location: str | None = None,
) -> asyncio.subprocess.Process:
    cmd = [
        "cargo",
        "run",
        "--",
        "url",
        "--website",
        website,
        "--run-id",
        run_id,
    ]

    if industry:
        cmd.extend(["--industry", industry])
    if location:
        cmd.extend(["--location", location])

    return await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(SCRAPER_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )