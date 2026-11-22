from aiogram.fsm.state import State, StatesGroup


class Auth(StatesGroup):
    password = State()
    position = State()


class TaskCreate(StatesGroup):
    content = State()
    pos = State()
    closers = State()
    deadline = State()


class WorkSubmit(StatesGroup):
    content = State()


class Grade(StatesGroup):
    grade = State()
    result = State()
    comment = State()
    photo = State()


class ChecklistCreate(StatesGroup):
    title = State()
    deadline = State()
    bonus = State()
    items = State()
    assign = State()
    checker = State()


class ChecklistProof(StatesGroup):
    content = State()


class PunishCreate(StatesGroup):
    user = State()
    kind = State()
    params = State()
    deadline = State()


class PunishReport(StatesGroup):
    content = State()


class Reject(StatesGroup):
    reason = State()


class ReminderCreate(StatesGroup):
    text = State()
    photo = State()
    target = State()
    mode = State()
    datetime_in = State()
    weekly = State()
    dates = State()
    time_mode = State()
    time_one = State()
    time_users = State()


class MaterialCreate(StatesGroup):
    kind = State()
    title = State()
    content = State()
    url = State()
    visible = State()
    users = State()


class Announcement(StatesGroup):
    content = State()


class TemplateCreate(StatesGroup):
    title = State()
    text = State()
    pos = State()
    photo = State()


class PasswordChange(StatesGroup):
    key = State()
    value = State()


class RoleGrant(StatesGroup):
    user = State()
    level = State()


class DeleteUser(StatesGroup):
    user = State()
    confirm = State()


class SearchUser(StatesGroup):
    query = State()


class BanUser(StatesGroup):
    user = State()
    action = State()


class CuratorAdd(StatesGroup):
    user = State()
    pos = State()


class GroupAdd(StatesGroup):
    type = State()
    chat = State()


class RightsEdit(StatesGroup):
    user = State()
    right = None


class VoteReason(StatesGroup):
    text = State()


class AppealStart(StatesGroup):
    confirm = State()


class FormCreate(StatesGroup):
    title = State()
    fields = State()
