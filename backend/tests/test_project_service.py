from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.models.enums import MemberRole
from app.services.project_service import ProjectService


def build_service():
    db = MagicMock()
    projects = MagicMock()
    users = MagicMock()
    return ProjectService(db, projects, users), db, projects, users


def test_invalid_project_dates_do_not_mutate_loaded_project():
    service, db, _, _ = build_service()
    project = SimpleNamespace(name="기존 프로젝트", started_on=date(2026, 8, 1), due_on=date(2026, 8, 31), status="ACTIVE")

    with pytest.raises(BusinessError) as error:
        service.update(project, {"started_on": date(2026, 9, 1)})

    assert error.value.error_code is ErrorCode.INVALID_PROJECT_DATES
    assert project.started_on == date(2026, 8, 1)
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_project_can_be_archived_without_losing_other_values():
    service, db, _, _ = build_service()
    project = SimpleNamespace(name="운영 프로젝트", started_on=None, due_on=None, status="ACTIVE")

    updated = service.update(project, {"status": "ARCHIVED"})

    assert updated.status == "ARCHIVED"
    assert updated.name == "운영 프로젝트"
    db.commit.assert_called_once()


def test_pending_invitation_cannot_be_sent_twice():
    service, db, projects, users = build_service()
    project = SimpleNamespace(id=10)
    inviter = SimpleNamespace(id=1)
    invitee = SimpleNamespace(id=2)
    users.get_by_login_id.return_value = invitee
    projects.get_member.return_value = None
    projects.get_project_invitation.return_value = SimpleNamespace(status="PENDING")

    with pytest.raises(BusinessError) as error:
        service.invite_member(project, inviter, "invitee", MemberRole.EDITOR)

    assert error.value.error_code is ErrorCode.DUPLICATE_INVITATION
    projects.save_invitation.assert_not_called()
    db.commit.assert_not_called()
