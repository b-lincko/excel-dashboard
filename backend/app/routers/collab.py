from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import database, notify
from ..security import require_permission, user_permissions

router = APIRouter(tags=["collab"])


class ChatThreadIn(BaseModel):
    kind: str = "channel"
    title: str = ""
    username: str = ""


class ChatMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: str = "active"
    owner: str = ""
    description: str = ""
    start_date: str = ""
    due_date: str = ""


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    owner: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    status: str = "open"
    assignee: str = ""
    due_date: str = ""
    notes: str = ""


class TaskPatch(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


class LinkIn(BaseModel):
    record_id: str = Field(min_length=1)


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    filters: dict[str, Any] = Field(default_factory=dict)
    shared: bool = False


class NotificationsReadIn(BaseModel):
    ids: Optional[list[int]] = None


@router.get("/api/chat/people")
def chat_people(user=Depends(require_permission("view"))):
    people = [
        {"username": u["username"], "full_name": u.get("full_name") or "", "role": u.get("role")}
        for u in database.list_users()
        if u.get("is_active")
    ]
    return {"items": people}


@router.get("/api/chat/threads")
def chat_threads(user=Depends(require_permission("view"))):
    return {"items": database.list_chat_threads(user["username"])}


@router.post("/api/chat/threads")
def create_thread(body: ChatThreadIn, user=Depends(require_permission("view"))):
    kind = (body.kind or "channel").strip().lower()
    if kind == "direct":
        other = (body.username or "").strip()
        if not other or other == user["username"]:
            raise HTTPException(status_code=400, detail="Choose another employee for a direct message.")
        if not database.get_user_by_username(other):
            raise HTTPException(status_code=404, detail="That user was not found.")
        return {"item": database.get_or_create_dm(user["username"], other)}
    title = (body.title or "").strip() or "New channel"
    return {"item": database.create_chat_thread("channel", title, user["username"], [user["username"]])}


@router.get("/api/chat/threads/{thread_id}")
def get_thread(thread_id: int, user=Depends(require_permission("view"))):
    if not database.user_can_access_thread(thread_id, user["username"]):
        raise HTTPException(status_code=404, detail="Thread not found")
    item = database.get_chat_thread(thread_id)
    return {"item": item}


@router.get("/api/chat/threads/{thread_id}/messages")
def list_messages(
    thread_id: int,
    after: int = 0,
    limit: int = 200,
    user=Depends(require_permission("view")),
):
    if not database.user_can_access_thread(thread_id, user["username"]):
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"items": database.list_chat_messages(thread_id, after_id=after, limit=limit)}


@router.post("/api/chat/threads/{thread_id}/messages")
def post_message(thread_id: int, body: ChatMessageIn, user=Depends(require_permission("view"))):
    if not database.user_can_access_thread(thread_id, user["username"]):
        raise HTTPException(status_code=404, detail="Thread not found")
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    item = database.add_chat_message(thread_id, user["username"], text)
    thread = database.get_chat_thread(thread_id) or {}
    pinged = notify.fanout_mentions(
        user["username"],
        text,
        thread_id=thread_id,
        record_id=str(thread.get("record_id") or ""),
        work_order_id=str(thread.get("work_order_id") or ""),
    )
    if thread.get("kind") == "work_order" and thread.get("record_id"):
        notify.notify_watchers(
            user["username"],
            {"record_id": thread.get("record_id"), "work_order_id": thread.get("work_order_id")},
            f"{user['username']} commented on {thread.get('title') or thread.get('work_order_id')}",
            skip=set(pinged),
        )
    return {"item": item}


@router.get("/api/notifications")
def list_notifications(limit: int = 40, unread: int = 0, user=Depends(require_permission("view"))):
    items = database.list_notifications(user["username"], unread_only=bool(unread), limit=limit)
    return {"items": items, "unread": database.unread_notification_count(user["username"])}


@router.post("/api/notifications/read")
def read_notifications(body: NotificationsReadIn, user=Depends(require_permission("view"))):
    marked = database.mark_notifications_read(user["username"], body.ids)
    return {"marked": marked, "unread": database.unread_notification_count(user["username"])}


@router.get("/api/views")
def list_views(user=Depends(require_permission("view"))):
    return {"items": database.list_saved_views(user["username"])}


@router.post("/api/views")
def create_view(body: SavedViewIn, user=Depends(require_permission("view"))):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    item = database.create_saved_view(name, user["username"], body.filters or {}, shared=bool(body.shared))
    return {"item": item}


@router.delete("/api/views/{view_id}")
def delete_view(view_id: int, user=Depends(require_permission("view"))):
    admin = user.get("role") == "admin" or "users" in user_permissions(user)
    if not database.delete_saved_view(view_id, user["username"], admin=admin):
        raise HTTPException(status_code=404, detail="Saved view not found")
    return {"deleted": True, "id": view_id}


@router.get("/api/projects")
def list_projects(user=Depends(require_permission("view"))):
    return {"items": database.list_projects()}


@router.post("/api/projects")
def create_project(body: ProjectIn, user=Depends(require_permission("edit"))):
    item = database.create_project(
        name=body.name.strip(),
        created_by=user["username"],
        status=body.status or "active",
        owner=body.owner or user["username"],
        description=body.description or "",
        start_date=body.start_date or "",
        due_date=body.due_date or "",
    )
    return {"item": item}


@router.get("/api/projects/{project_id}")
def get_project(project_id: int, user=Depends(require_permission("view"))):
    item = database.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"item": item}


@router.put("/api/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, user=Depends(require_permission("edit"))):
    if not database.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    item = database.update_project(project_id, **body.model_dump(exclude_unset=True))
    return {"item": item}


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: int, user=Depends(require_permission("edit"))):
    if not database.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"deleted": True, "id": project_id}


@router.post("/api/projects/{project_id}/tasks")
def add_task(project_id: int, body: TaskIn, user=Depends(require_permission("edit"))):
    if not database.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    item = database.add_project_task(
        project_id,
        title=body.title.strip(),
        assignee=body.assignee,
        due_date=body.due_date,
        notes=body.notes,
        status=body.status or "open",
    )
    return {"item": item}


@router.put("/api/projects/{project_id}/tasks/{task_id}")
def patch_task(project_id: int, task_id: int, body: TaskPatch, user=Depends(require_permission("edit"))):
    if not database.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    item = database.update_project_task(task_id, **body.model_dump(exclude_unset=True))
    if not item or int(item.get("project_id") or 0) != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"item": item}


@router.delete("/api/projects/{project_id}/tasks/{task_id}")
def remove_task(project_id: int, task_id: int, user=Depends(require_permission("edit"))):
    if not database.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if not database.delete_project_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True, "id": task_id}


@router.post("/api/projects/{project_id}/links")
def link_wo(project_id: int, body: LinkIn, user=Depends(require_permission("edit"))):
    if not database.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    database.link_project_wo(project_id, body.record_id.strip())
    return {"item": database.get_project(project_id)}


@router.delete("/api/projects/{project_id}/links/{record_id}")
def unlink_wo(project_id: int, record_id: str, user=Depends(require_permission("edit"))):
    if not database.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    database.unlink_project_wo(project_id, record_id)
    return {"item": database.get_project(project_id)}
