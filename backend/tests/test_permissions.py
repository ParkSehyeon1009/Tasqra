from types import SimpleNamespace

import pytest

from app.core.exceptions import BusinessError
from app.dependencies import ProjectAccess, get_project_editor_access, get_project_owner_access


def access(role: str, *, owner_id: int = 1, user_id: int = 1) -> ProjectAccess:
    return ProjectAccess(
        project=SimpleNamespace(id=10, owner_id=owner_id),
        member=SimpleNamespace(user_id=user_id, role=role),
    )


@pytest.mark.parametrize("role", ["OWNER", "EDITOR"])
def test_owner_and_editor_can_edit_project(role):
    project_access = access(role, user_id=1 if role == "OWNER" else 2)
    assert get_project_editor_access(project_access) is project_access


def test_viewer_cannot_edit_project():
    with pytest.raises(BusinessError) as error:
        get_project_editor_access(access("VIEWER", user_id=2))
    assert error.value.error_code.status_code == 403


@pytest.mark.parametrize("role,user_id", [("EDITOR", 2), ("VIEWER", 2), ("OWNER", 2)])
def test_only_actual_owner_can_manage_members_or_delete(role, user_id):
    with pytest.raises(BusinessError) as error:
        get_project_owner_access(access(role, owner_id=1, user_id=user_id))
    assert error.value.error_code.status_code == 403


def test_owner_can_manage_members_and_delete():
    project_access = access("OWNER")
    assert get_project_owner_access(project_access) is project_access
