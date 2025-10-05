"""Backward compatibility shim for legacy imports.

This project now exposes the job APIs from :mod:`app.jobs2`.  Some older
scripts or deployment setups still import :mod:`app.jobs`, so we keep this
module as a thin wrapper that simply re-exports the public call points from
``jobs2``.  Keeping the wrapper in UTF-8 also avoids encoding issues during
static checks.
"""

from . import jobs2 as _jobs2

# Re-export the blueprint and helper used by the application factory.
jobs_bp = _jobs2.jobs_bp
attach_app = _jobs2.attach_app

# Optional endpoints that may be imported by extensions or tooling.
preview_local_asset = _jobs2.preview_local_asset
list_workflows = _jobs2.list_workflows_api
get_workflow_form = _jobs2.get_workflow_form
create_job = _jobs2.create_job
job_status = _jobs2.job_status
queue_overview = _jobs2.queue_overview
proxy_view = _jobs2.proxy_view
job_proxy_view = _jobs2.job_proxy_view
job_artifacts = _jobs2.job_artifacts
list_jobs = _jobs2.list_jobs
download_single = _jobs2.download_single
download_zip = _jobs2.download_zip
health = _jobs2.health

__all__ = [
    "jobs_bp",
    "attach_app",
    "preview_local_asset",
    "list_workflows",
    "get_workflow_form",
    "create_job",
    "job_status",
    "queue_overview",
    "proxy_view",
    "job_proxy_view",
    "job_artifacts",
    "list_jobs",
    "download_single",
    "download_zip",
    "health",
]
