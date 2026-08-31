# ① 책임: 결정사항·일정 추출 결과를 기존 ORM 행으로 추가하고 flush한다.
# ② 관계: decision_schedule_writer.py가 호출하며, commit/rollback은 상위 서비스 트랜잭션이 맡는다.
# ③ Spring 비교: JpaRepository.saveAll()처럼 영속화만 담당하고 @Transactional 경계는 열지 않는다.

from sqlalchemy.orm import Session

from app.models.decision import Decision
from app.models.schedule import ScheduleItem


class DecisionScheduleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add_decisions(self, rows: list[Decision]) -> list[Decision]:
        if rows:
            self._db.add_all(rows)
            self._db.flush()
        return rows

    def add_schedule_items(
        self, rows: list[ScheduleItem]
    ) -> list[ScheduleItem]:
        if rows:
            self._db.add_all(rows)
            self._db.flush()
        return rows
