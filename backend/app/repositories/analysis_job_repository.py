from sqlalchemy import select, update

from app.models.analysis_job import AnalysisJob
from app.models.document import Analysis


class AnalysisJobRepository:
    def __init__(self, db):
        self.db = db

    def get(self, project_id, document_id, job_id, *, lock=False):
        stmt = select(AnalysisJob).where(AnalysisJob.id == job_id,
            AnalysisJob.project_id == project_id, AnalysisJob.document_id == document_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.db.scalar(stmt)

    def latest(self, project_id, document_id):
        return self.db.scalar(select(AnalysisJob).where(AnalysisJob.project_id == project_id,
            AnalysisJob.document_id == document_id).order_by(AnalysisJob.created_at.desc()).limit(1))

    def active(self, document_id):
        return self.db.scalar(select(AnalysisJob).where(AnalysisJob.document_id == document_id,
            AnalysisJob.status.in_(("PENDING", "RUNNING"))).with_for_update())

    def add(self, job):
        self.db.add(job)
        self.db.flush()
        return job

    def progress(self, job_id, stage, done, total):
        self.db.execute(update(AnalysisJob).where(AnalysisJob.id == job_id,
            AnalysisJob.status == "RUNNING").values(stage=stage, completed_units=done, total_units=total))

    def results(self, job):
        if not job.analysis_ids:
            return []
        return self.db.scalars(select(Analysis).where(Analysis.document_id == job.document_id,
            Analysis.id.in_(job.analysis_ids)).order_by(Analysis.id)).all()
