from datetime import datetime, timezone

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional


class TaskSuggestionService:
    def __init__(self, db, suggestions, task_service):
        self._db = db
        self._suggestions = suggestions
        self._tasks = task_service

    @staticmethod
    def _row(item):
        from app.schemas.task_suggestion import TaskSuggestionRow
        return TaskSuggestionRow.model_validate(item, from_attributes=True)

    def list(self, project_id, decisions, limit, document_id=None):
        from app.schemas.task_suggestion import TaskSuggestionListResponse
        rows, total = self._suggestions.list(project_id, decisions, limit, document_id)
        return TaskSuggestionListResponse(items=[self._row(row) for row in rows], total=total)

    def approve(self, project_id, item_id, user_id, values=None):
        item = self._get(project_id, item_id)
        if item.created_task_id is not None:
            return self._row(item)
        values = values or {}
        title = values.get("title") or item.title
        description = values.get("description", item.description)
        due_on = values.get("due_on", item.due_on)
        assignee_id = values.get("assignee_id")
        with transactional(self._db):
            existing_task_id = self._suggestions.existing_task_id(
                project_id, item.document_id, item.evidence_fingerprint)
            if existing_task_id is None:
                task = self._tasks.create_in_transaction(project_id, user_id, {"title": title,
                    "description": description, "type": "DOCUMENT", "due_on": due_on,
                    "assignee_id": assignee_id}, origin="AI_APPROVED",
                    source_suggestion_id=item.id)
                item.created_task_id = task.id
            else:
                item.created_task_id = existing_task_id
            item.decision = "EDITED" if values else "APPROVED"
            item.decided_by = user_id
            item.decided_at = datetime.now(timezone.utc)
        return self._row(item)

    def reject(self, project_id, item_id, user_id):
        item = self._get(project_id, item_id)
        with transactional(self._db):
            item.decision = "REJECTED"
            item.decided_by = user_id
            item.decided_at = datetime.now(timezone.utc)
        return self._row(item)

    def cancel(self, project_id, item_id):
        item = self._get(project_id, item_id)
        if item.created_task_id is not None:
            raise BusinessError(ErrorCode.TASK_SUGGESTION_ALREADY_APPROVED)
        with transactional(self._db):
            item.decision = "PENDING"; item.decided_by = None; item.decided_at = None
        return self._row(item)

    def _get(self, project_id, item_id):
        item = self._suggestions.get(project_id, item_id)
        if item is None:
            raise BusinessError(ErrorCode.TASK_SUGGESTION_NOT_FOUND)
        return item
