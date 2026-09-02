from sqlalchemy import func

from app.models.task_suggestion import TaskSuggestion


class TaskSuggestionRepository:
    def __init__(self, db):
        self._db = db

    def add_all(self, rows):
        if rows:
            self._db.add_all(rows)
            self._db.flush()
        return rows

    def delete_pending(self, project_id, document_id):
        """재분석 전 아직 검토하지 않은 이전 후보만 교체한다."""
        self._db.query(TaskSuggestion).filter_by(
            project_id=project_id, document_id=document_id,
            decision="PENDING").delete(synchronize_session=False)

    def get(self, project_id, item_id):
        return self._db.query(TaskSuggestion).filter_by(
            project_id=project_id, id=item_id).one_or_none()

    def list(self, project_id, decisions, limit, document_id=None):
        query = self._db.query(TaskSuggestion).filter(
            TaskSuggestion.project_id == project_id,
            TaskSuggestion.decision.in_(decisions))
        if document_id is not None:
            query = query.filter(TaskSuggestion.document_id == document_id)
        total = query.with_entities(func.count(TaskSuggestion.id)).scalar() or 0
        rows = query.order_by(TaskSuggestion.quality_score.desc(),
            TaskSuggestion.created_at, TaskSuggestion.id).limit(limit).all()
        return rows, int(total)
