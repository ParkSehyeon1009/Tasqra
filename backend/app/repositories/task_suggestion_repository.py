from sqlalchemy import func

from app.models.document import Analysis
from app.models.task_suggestion import TaskSuggestion
from app.models.task import Task


class TaskSuggestionRepository:
    def __init__(self, db):
        self._db = db

    def add_all(self, rows):
        if rows:
            self._db.add_all(rows)
            self._db.flush()
        return rows

    def delete_pending(self, project_id, document_id, *, analyzer_type):
        """재분석 전 아직 검토하지 않은 이전 후보만 교체한다.

        🔴 **analyzer_type 으로 좁혀야 한다.** 이 테이블에 쓰는 분석기가 둘이다
          (action_task·features). 문서 단위로 지우면 **한 번의 분석 안에서 뒤에
          도는 분석기가 앞의 결과를 지운다.**

          2026-09-07 실측: 과업지시서 하나에서 action_task 9건이 저장된 뒤
          features 가 저장하면서 그 9건을 지우고 12건만 남겼다. 사용자에게는
          「이행 의무가 사라진」 것으로 보인다.

        ⚠️ analyzer_type 은 **키워드 필수**다. 기본값을 두면 부르는 쪽이 빠뜨려도
          조용히 예전 동작(전부 삭제)으로 돌아간다.

        ⚠️ analysis_id 가 비어 있는 행은 지우지 않는다. 어느 분석기가 만든 것인지
          알 수 없어 남의 것을 지울 위험이 있다. analyses 행이 지워진 경우에만
          생기며(ondelete SET NULL) 드물다.
        """
        만든분석 = (self._db.query(Analysis.id)
                    .filter(Analysis.document_id == document_id,
                            Analysis.analyzer_type == analyzer_type))
        (self._db.query(TaskSuggestion)
         .filter(TaskSuggestion.project_id == project_id,
                 TaskSuggestion.document_id == document_id,
                 TaskSuggestion.decision == "PENDING",
                 TaskSuggestion.analysis_id.in_(만든분석))
         .delete(synchronize_session=False))

    def get(self, project_id, item_id):
        return self._db.query(TaskSuggestion).filter_by(
            project_id=project_id, id=item_id).one_or_none()

    def existing_task_id(self, project_id, document_id, evidence_fingerprint):
        if not evidence_fingerprint:
            return None
        row = (self._db.query(Task.id)
            .join(TaskSuggestion, Task.source_suggestion_id == TaskSuggestion.id)
            .filter(Task.project_id == project_id,
                    TaskSuggestion.document_id == document_id,
                    TaskSuggestion.evidence_fingerprint == evidence_fingerprint)
            .order_by(Task.id)
            .first())
        return int(row[0]) if row else None

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
