import json
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import config
import database as db
import services
import keyboards
from states import *
from utils import kb, user_line, fmt_name

router = Router()


def settings_password(key):
    return db.setting(key, config.DEFAULT_PASSWORDS[key])


@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    u = db.get_user(m.from_user.id)
    if not u:
        await state.set_state(Auth.password)
        await m.answer("👋 Добро пожаловать в TANKERS-BOT!\n\nВведите пароль для входа:",
                       reply_markup=keyboards.rkb([["❌ Отмена"]]))
        return
    if u["leave_at"]:
        db.execute("UPDATE users SET leave_at=NULL WHERE id=?", (u["id"],))
        services.log(u["id"], "return")
    if u["banned"]:
        await m.answer("🚫 Вы заблокированы в боте.")
        return
    await m.answer("🏠 Главное меню:", reply_markup=keyboards.main_menu(u))


@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    u = db.get_user(m.from_user.id)
    await m.answer("❌ Отменено. Главное меню:",
                   reply_markup=keyboards.main_menu(u) if u else None)


@router.message(Auth.password, F.text)
async def auth_password(m: Message, state: FSMContext):
    if m.text == "❌ Отмена":
        await state.clear()
        return
    pw = m.text.strip()
    uid = m.from_user.id
    name = m.from_user.first_name or f"id{uid}"
    pw_owner = settings_password("pw_owner")
    pw_admin = settings_password("pw_admin")
    pw_user = settings_password("pw_user")
    exists = db.get_user(uid)

    if pw == pw_owner:
        role, level, status = 4, 4, "owner"
    elif pw == pw_admin:
        role, level, status = 1, 1, "newbie"
    elif pw == pw_user:
        role, level, status = 0, 0, "newbie"
    else:
        db.log_action(uid, "auth_fail", "")
        await m.answer("❌ Неверный пароль. Попробуйте ещё раз или /cancel")
        return

    if not exists:
        db.execute(
            "INSERT INTO users(id,name,role,admin_level,pos,status,points,"
            "timezone,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (uid, name, role, level, None, status, 0, "Europe/Moscow", db.now()))
    else:
        db.execute("UPDATE users SET role=?, admin_level=?, leave_at=NULL WHERE id=?",
                   (max(exists["role"], role) if exists["role"] >= 4 else role,
                    level, uid))
    if role == 1 and not db.get_user(uid)["rights"]:
        db.execute("UPDATE users SET rights=? WHERE id=?",
                   (json.dumps(config.DEFAULT_RIGHTS[1]), uid))

    u = db.get_user(uid)
    await state.set_state(Auth.position)
    await m.answer(f"🎉 Добро пожаловать, {name}! Ваша роль: {config.ROLE_NAMES[role]}",
                   reply_markup=keyboards.rkb([["🏠 Меню"]]))
    await m.answer("💼 Выберите должность:", reply_markup=keyboards.pos_kb())
    services.log(uid, "auth", config.ROLE_NAMES[role])
    try:
        await m.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("pos:"))
async def choose_pos(c: CallbackQuery, state: FSMContext):
    pos = c.data.split(":")[1]
    u = db.get_user(c.from_user.id)
    if not u:
        await c.answer("Сначала авторизуйтесь /start", show_alert=True)
        return
    db.execute("UPDATE users SET pos=? WHERE id=?",
               (None if pos == "none" else pos, u["id"]))
    services.log(u["id"], "pos", pos)
    await state.clear()
    await c.message.edit_text(
        f"✅ Должность сохранена: "
        f"{config.POSITIONS.get(pos, 'Без должности') if pos != 'none' else 'Без должности'}")
    await c.message.answer("🏠 Главное меню:", reply_markup=keyboards.main_menu(u))
    await c.answer()


@router.message(F.text == "🏠 Меню")
async def menu_home(m: Message, state: FSMContext):
    await state.clear()
    u = db.get_user(m.from_user.id)
    if not u:
        await cmd_start(m, state)
        return
    await m.answer("🏠 Главное меню:", reply_markup=keyboards.main_menu(u))


@router.callback_query(F.data.startswith("back:"))
async def back_cb(c: CallbackQuery, state: FSMContext):
    await state.clear()
    u = db.get_user(c.from_user.id)
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.message.answer("🏠 Главное меню:",
                           reply_markup=keyboards.main_menu(u) if u else None)
    await c.answer()


@router.message(F.text == "👤 Профиль")
async def profile(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    created = u["created_at"] or db.now()
    try:
        days = (datetime.now() - datetime.strptime(created[:10], "%Y-%m-%d")).days
    except Exception:
        days = 0
    lines = [
        "👤 Профиль\n",
        f"Имя: {u['name']}",
        f"ID: {u['id']}",
        f"Роль: {config.ROLE_NAMES[u['role']]}",
        f"Должность: {config.POSITIONS.get(u['pos'], '—')}",
        f"Статус: {config.STATUS_NAMES.get(u['status'], u['status'])}",
        f"Баллы: {u['points']:.1f}",
        f"Часовой пояс: {u['timezone']}",
        f"В проекте: {days} дн.",
    ]
    works = db.get("SELECT COUNT(*) c FROM works WHERE user_id=? AND status='reviewed'",
                   (u["id"],))["c"]
    lines.append(f"Работ с оценкой: {works}")
    if u["status"] == "newbie":
        accepted = db.get(
            "SELECT COUNT(*) c FROM works WHERE user_id=? AND status='reviewed' AND "
            "result IN ('🟡 Частично верно','🟢 Правильно')", (u["id"],))["c"]
        lines.append(f"До Участника: осталось {max(0, 7 - days)} дн. и "
                     f"{max(0, 1 - accepted)} принятая работа ({accepted}/1)")
    elif u["status"] == "member":
        lines.append(f"До Лучшего: {u['points']:.0f}/{config.PROMOTE_BEST}")
    elif u["status"] in ("best", "candidate"):
        lines.append(f"До Ведущего: {u['points']:.0f}/{config.PROMOTE_LEAD}")
    punish = db.query(
        "SELECT * FROM punishments WHERE user_id=? AND status IN ('active','rejected')",
        (u["id"],))
    if punish:
        lines.append("")
        lines.append("⚠️ Активные наказания:")
        for p in punish:
            lines.append(f"#{p['id']} {config.PUNISH_KINDS[p['kind']]} — {p['topic'] or ''} "
                         f"(до {(p['deadline'] or '—')[:10]})")
    kbd_rows = []
    for p in punish:
        if p["kind"] != "warning" and p["kind"] != "points":
            kbd_rows.append(["📤 Сдать отчёт", f"preport:{p['id']}"])
    last_reject = db.get(
        "SELECT * FROM votes WHERE target_id=? AND status='closed' AND type IN "
        "('best','lead') ORDER BY id DESC LIMIT 1", (u["id"],))
    if last_reject:
        appeal_type = ("best" if last_reject["type"] == "best" else "lead") + "_appeal"
        done_appeals = db.get(
            "SELECT COUNT(*) c FROM votes WHERE target_id=? AND type LIKE ?",
            (u["id"], appeal_type + "%"))["c"]
        if done_appeals < 2:
            kbd_rows.append(["📣 Подать апелляцию",
                             f"appeal_start:{appeal_type}{'1' if done_appeals == 0 else '2'}:"
                             f"{u['id']}"])
    kbd_rows.append(["⬅️ Назад", "back:menu"])
    await m.answer("\n".join(lines), reply_markup=kb(kbd_rows))


@router.message(F.text == "💼 Должность")
async def change_pos(m: Message):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await m.answer("💼 Выберите должность:", reply_markup=keyboards.pos_kb())


@router.callback_query(F.data.startswith("vote:"))
async def do_vote(c: CallbackQuery):
    _, vid, choice = c.data.split(":")
    vid = int(vid)
    vote = db.get("SELECT * FROM votes WHERE id=?", (vid,))
    if not vote or vote["status"] != "active":
        await c.answer("Голосование завершено", show_alert=True)
        return
    u = db.get_user(c.from_user.id)
    if not u or c.from_user.id not in services.vote_approvers(vote["type"], vote["target_id"]):
        await c.answer("Вы не участвуете в этом голосовании", show_alert=True)
        return
    await services.vote_cast(vid, c.from_user.id, choice)
    await services.vote_finish(vid)
    try:
        await c.message.edit_text(c.message.text + ("\n\n✅ Голос учтён: ЗА" if choice == "yes"
                                                    else "\n\n❌ Голос учтён: ПРОТИВ"))
    except Exception:
        pass
    await c.answer("Голос учтён")


@router.message(Command("id"))
async def cmd_id(m: Message):
    chat = m.chat
    thread = m.message_thread_id or 0
    await m.answer(f"chat_id: <code>{chat.id}</code>\n"
                   f"thread_id: <code>{thread}</code>\n"
                   f"Тип чата: {chat.type}")


@router.message(Command("help"))
async def cmd_help(m: Message):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await m.answer(
        "ℹ️ Команды:\n"
        "/start — вход и меню\n"
        "/cancel — отмена действия\n"
        "/id — ID чата и темы (в группах)\n"
        "/help — эта справка")
