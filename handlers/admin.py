import json
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import config
import database as db
import services
import keyboards
from handlers.tasks import delete_task
from states import *
from utils import kb, send_content, file_list_from_message, fmt_name, user_line, \
    parse_dt, parse_time

router = Router()

CB_RIGHTS = {"ad:punish": "punishments", "ad:materials": "materials",
             "ad:reminders": "reminders", "ad:announce": "announcements",
             "ad:curators": "curators", "ad:publish": "publish", "ad:stats": "stats",
             "ad:trash": "trash", "ad:search": "search", "ad:logs": "logs",
             "ad:csv": "export", "ad:bans": "bans", "ad:templates": "templates",
             "ad:forms": "tasks"}


def allowed_cb(u, cb):
    cb = cb.split(":")[0]
    if cb not in CB_RIGHTS:
        return True
    return db.has_right(u, CB_RIGHTS[cb])


@router.message(F.text == "🛠 Админ-панель")
async def admin_panel(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u or u["role"] < 1:
        return
    await state.clear()
    rows = []
    if db.has_right(u, "tasks"):
        rows.append(["➕ Создать задание", "t:new"])
        rows.append(["⏳ Работы на проверке", "ad:queue"])
        if db.has_right(u, "templates"):
            rows.append(["📑 Шаблоны", "ad:templates"])
        rows.append(["📄 Формы", "ad:forms"])
    if db.has_right(u, "checklists"):
        rows.append(["✅ Чек-листы", "ad:checklists"])
    if db.has_right(u, "punishments"):
        rows.append(["⚖️ Наказания", "ad:punish"])
    if db.has_right(u, "materials"):
        rows.append(["📚 Материалы", "ad:materials"])
    if db.has_right(u, "announcements"):
        rows.append(["📢 Объявление", "ad:announce"])
    if db.has_right(u, "reminders"):
        rows.append(["⏰ Напоминания", "ad:reminders"])
    if db.has_right(u, "curators"):
        rows.append(["🧑‍🏫 Кураторы", "ad:curators"])
    if db.has_right(u, "publish"):
        rows.append(["📍 Публикация", "ad:publish"])
    if db.has_right(u, "stats"):
        rows.append(["📊 Статистика", "ad:stats"])
    if db.has_right(u, "trash"):
        rows.append(["🗑 Корзина/Архив", "ad:trash"])
    if db.has_right(u, "search"):
        rows.append(["🔎 Поиск участников", "ad:search"])
    if db.has_right(u, "logs"):
        rows.append(["📜 Логи", "ad:logs"])
    if db.has_right(u, "export"):
        rows.append(["📤 Экспорт CSV", "ad:csv"])
    if db.has_right(u, "bans"):
        rows.append(["🚫 Баны", "ad:bans"])
    rows.append(["🏠 Меню", "back:menu"])
    await m.answer(f"🛠 Админ-панель ({config.ROLE_NAMES[u['role']]})\n"
                   f"Уровень: {u['admin_level']}", reply_markup=kb(rows))


@router.message(F.text == "⚙️ Владелец")
async def owner_panel(m: Message):
    u = db.get_user(m.from_user.id)
    if not u or u["role"] < 4:
        return
    await m.answer("⚙️ Панель владельца:", reply_markup=kb([
        ["🔐 Пароли", "ow:passwords"], ["👥 Права админов", "ow:rights"],
        ["👑 Выдать роль", "ow:roles"], ["🗑 Удалить участника", "ow:delete"],
        ["🌍 Часовые пояса участников", "ow:tz"],
        ["⬅️ Админ-панель", "ad:topanel"], ["🏠 Меню", "back:menu"]]))


@router.callback_query(F.data == "ad:topanel")
async def ad_back(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not u or u["role"] < 1:
        await c.answer()
        return
    
    await c.message.delete()
    await c.message.answer(f"🛠 Админ-панель ({config.ROLE_NAMES[u['role']]})",
                           reply_markup=await task_admin_kb(u))
    await c.answer()


async def task_admin_kb(u):
    rows = []
    if db.has_right(u, "tasks"):
        rows.append(["➕ Создать задание", "t:new"])
        rows.append(["⏳ Работы на проверке", "ad:queue"])
        if db.has_right(u, "templates"):
            rows.append(["📑 Шаблоны", "ad:templates"])
        rows.append(["📄 Формы", "ad:forms"])
    if db.has_right(u, "checklists"):
        rows.append(["✅ Чек-листы", "ad:checklists"])
    if db.has_right(u, "punishments"):
        rows.append(["⚖️ Наказания", "ad:punish"])
    if db.has_right(u, "materials"):
        rows.append(["📚 Материалы", "ad:materials"])
    if db.has_right(u, "announcements"):
        rows.append(["📢 Объявление", "ad:announce"])
    if db.has_right(u, "reminders"):
        rows.append(["⏰ Напоминания", "ad:reminders"])
    if db.has_right(u, "curators"):
        rows.append(["🧑‍🏫 Кураторы", "ad:curators"])
    if db.has_right(u, "publish"):
        rows.append(["📍 Публикация", "ad:publish"])
    if db.has_right(u, "stats"):
        rows.append(["📊 Статистика", "ad:stats"])
    if db.has_right(u, "trash"):
        rows.append(["🗑 Корзина/Архив", "ad:trash"])
    if db.has_right(u, "search"):
        rows.append(["🔎 Поиск участников", "ad:search"])
    if db.has_right(u, "logs"):
        rows.append(["📜 Логи", "ad:logs"])
    if db.has_right(u, "export"):
        rows.append(["📤 Экспорт CSV", "ad:csv"])
    if db.has_right(u, "bans"):
        rows.append(["🚫 Баны", "ad:bans"])
    rows.append(["🏠 Меню", "back:menu"])
    return kb(rows)


@router.callback_query(F.data.startswith("ad:"))
async def admin_dispatch(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not u or u["role"] < 1:
        await c.answer()
        return
    key = c.data.split(":")[1]
    if key == "checklists":
        await c.message.answer("✅ Чек-листы:", reply_markup=kb(
            [["➕ Создать чек-лист", "cl:new"], ["⬅️ Назад", "back:menu"]]))
    elif key == "punish":
        await c.message.answer("⚖️ Наказания:", reply_markup=kb(
            [["➕ Выдать наказание", "p:new"], ["📋 Наказания участников", "p:all"],
             ["⬅️ Назад", "back:menu"]]))
    elif key == "materials":
        await c.message.answer("📚 Материалы:", reply_markup=kb(
            [["➕ Добавить материал", "mat:new"], ["📋 Управление", "mat:manage"],
             ["⬅️ Назад", "back:menu"]]))
    elif key == "reminders":
        await c.message.answer("⏰ Напоминания:", reply_markup=kb(
            [["➕ Создать напоминание", "rem:new"], ["📜 Активные", "rem:list"],
             ["⬅️ Назад", "back:menu"]]))
    elif key == "announce":
        await c.message.answer("📢 Используйте кнопку «📢 Объявления» в главном меню — "
                               "текст уйдёт в чаты и всем участникам.")
    elif key == "stats":
        await c.message.answer("📊 Статистика:", reply_markup=kb(
            [["📊 Моя неделя", "st:me"], ["📈 Отчёт по проекту", "st:project"],
             ["🤖 Автоанализ", "st:analysis"], ["🏆 Лучшие/худшие", "st:top"],
             ["⬅️ Назад", "back:menu"]]))
    elif key == "curators":
        await c.message.answer("🧑‍🏫 Кураторы:", reply_markup=kb(
            [["➕ Назначить куратора", "cur:new"], ["📜 Список", "cur:list"],
             ["⬅️ Назад", "back:menu"]]))
    elif key == "publish":
        await pub_menu(c)
    elif key == "trash":
        await trash_menu(c)
    elif key == "logs":
        await logs_show(c)
    elif key == "csv":
        await c.message.answer("📤 Что экспортировать?", reply_markup=kb([
            ["👥 Участники", "csv:users"], ["📤 Работы", "csv:works"],
            ["📜 Логи", "csv:logs"], ["⬅️ Назад", "back:menu"]]))
    elif key == "queue":
        await review_queue(c)
    elif key == "bans":
        await bans_menu(c)
    elif key == "templates":
        await templates_menu(c)
    elif key == "forms":
        await forms_menu(c)
    await c.answer()


async def review_queue(c):
    works = db.query("SELECT * FROM works WHERE status='submitted' ORDER BY id LIMIT 30")
    if not works:
        await c.message.answer("✅ Очередь пуста!")
        await c.answer()
        return
    rows = []
    for w in works:
        owner = db.get_user(w["user_id"])
        rows.append([f"#{w['id']} {owner['name'] if owner else '?'} — задание "
                     f"#{w['task_id']}", f"wr:view:{w['id']}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("⏳ Работы на проверке:", reply_markup=kb(rows))
    await c.answer()


async def logs_show(c):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "logs"):
        await c.answer("Нет прав", show_alert=True)
        return
    logs = db.query("SELECT * FROM logs ORDER BY id DESC LIMIT 20")
    text = "📜 Последние действия:\n\n" + "\n".join(
        f"[{l['ts'][5:16]}] id{l['user_id']}: {l['action']} {l['details']}" for l in logs)
    await c.message.answer(text)
    await c.answer()


async def pub_menu(c):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "publish"):
        await c.answer("Нет прав", show_alert=True)
        return
    groups = db.query("SELECT * FROM groups")
    lines = ["📍 Место публикации\n"]
    rows = []
    for g in groups:
        name = g["title"] or str(g["chat_id"])
        t = config.GROUP_TYPES.get(g["type"], g["type"])
        lines.append(f"{t}: {name} (тема {g['thread_id'] or 0}), "
                     f"{'♾ постоянная' if g['is_permanent'] else '1️⃣ одноразовая'}")
        rows.append([f"🗑 {t}: {name[:20]}", f"grdel:{g['id']}"])
    rows.append(["➕ Добавить чат", "gr:add"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("\n".join(lines), reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("gr:add"))
async def gr_add(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "publish"):
        await c.answer("Нет прав", show_alert=True)
        return
    rows = [[name, f"grt:{key}"] for key, name in config.GROUP_TYPES.items()]
    rows.append(["⬅️ Отмена", "ad:topanel"])
    await state.set_state(GroupAdd.type)
    await c.message.answer("📋 Для чего чат?", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("grt:"))
async def grt_pick(c: CallbackQuery, state: FSMContext):
    await state.update_data(gtype=c.data.split(":")[1])
    await state.set_state(GroupAdd.chat)
    await c.message.answer(
        "➕ Добавьте бота в чат, затем пришлите сюда chat_id (команда /id из чата) "
        "или в виде -1001234567:5 (chat_id:тема):")
    await c.answer()


@router.message(GroupAdd.chat, F.text)
async def gr_chat(m: Message, state: FSMContext):
    if m.text == "/cancel":
        await state.clear()
        return
    data = await state.get_data()
    tid = 0
    try:
        if ":" in m.text:
            cid_s, tid_s = m.text.split(":", 1)
            cid, tid = int(cid_s), int(tid_s)
        else:
            cid = int(m.text)
    except ValueError:
        await m.answer("Не понял. Пришлите chat_id (-100...) или chat_id:thread_id")
        return
    chat_title = None
    try:
        chat = await m.bot.get_chat(cid)
        chat_title = chat.title or chat.full_name
    except Exception:
        pass
    db.execute(
        "INSERT INTO groups(chat_id,thread_id,type,is_permanent,title) VALUES(?,?,?,?,1)",
        (cid, tid or None, data["gtype"], chat_title))
    await state.clear()
    u = db.get_user(m.from_user.id)
    services.log(u["id"], "group_add", f"{cid}:{tid} {data['gtype']}")
    await m.answer("✅ Чат добавлен как постоянное место публикации.",
                   reply_markup=keyboards.main_menu(u))


@router.callback_query(F.data.startswith("grdel:"))
async def gr_del(c: CallbackQuery):
    gid = int(c.data.split(":")[1])
    db.execute("DELETE FROM groups WHERE id=?", (gid,))
    services.log(c.from_user.id, "group_del", str(gid))
    await c.answer("Удалено")
    await pub_menu(c)


async def trash_menu(c):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "trash"):
        await c.answer("Нет прав", show_alert=True)
        return
    tr = db.query("SELECT * FROM trash ORDER BY deleted_at DESC LIMIT 30")
    rows = []
    tbl_icons = {"tasks": "📋", "checklists": "✅", "materials": "📚", "templates": "📑"}
    for r in tr:
        data = json.loads(r["data"])
        icon = tbl_icons.get(r["table_name"], "📄")
        title = data.get("title") or (data.get("text") or "")[:30] or str(r["row_id"])
        rows.append([f"{icon} {title[:32]} ({r['deleted_at'][5:16]})",
                     f"tr:restore:{r['id']}"])
    if not rows:
        await c.message.answer("🗑 Корзина пуста.")
        await c.answer()
    else:
        rows.append(["⬅️ Назад", "back:menu"])
        await c.message.answer("🗑 Корзина (48 ч на восстановление):",
                               reply_markup=kb(rows))
        await c.answer()
    arch = db.query("SELECT * FROM archive ORDER BY id DESC LIMIT 10")
    if arch:
        a_lines = ["🗄 Архив (последние):\n"]
        for a in arch:
            data = json.loads(a["data"])
            a_lines.append(f"• {a['table_name']} #{a['row_id']}: "
                           f"{(data.get('title') or data.get('text') or '')[:40]}")
        await c.message.answer("\n".join(a_lines))


@router.callback_query(F.data.startswith("tr:restore:"))
async def trash_restore(c: CallbackQuery):
    trid = int(c.data.split(":")[2])
    row = db.get("SELECT * FROM trash WHERE id=?", (trid,))
    if not row:
        await c.answer("Уже удалено", show_alert=True)
        return
    ok = db.restore_from_trash(trid)
    if ok and row["table_name"] in ("tasks", "checklists"):
        rid = row["row_id"]
        db.execute(f"UPDATE {row['table_name']} SET status='active' WHERE id=?", (rid,))
    services.log(c.from_user.id, "restore", str(trid))
    await c.answer("Восстановлено" if ok else "Ошибка")


async def bans_menu(c):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "bans"):
        await c.answer("Нет прав", show_alert=True)
        return
    banned = db.query("SELECT * FROM users WHERE banned=1")
    await c.message.answer("🚫 Баны\n\nЗаблокированные: " +
                           (", ".join(fmt_name(x) for x in banned) or "нет"),
                           reply_markup=kb([["🚫 Забанить", "ban:new"],
                                            ["♻️ Разбанить", "unban:new"],
                                            ["⬅️ Назад", "back:menu"]]))
    await c.answer()


async def _set_ban(target_id, ban, source_id):
    db.execute("UPDATE users SET banned=?, ban_src=? WHERE id=?",
               (ban, (f"admin {source_id}" if ban else None), target_id))


@router.callback_query(F.data.startswith("ban:new"))
async def ban_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "bans"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(BanUser.user)
    await c.message.answer("🚫 Пришлите ID участника для блокировки:")
    await c.answer()


@router.message(BanUser.user, F.text)
async def ban_uid(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not db.has_right(u, "bans"):
        return
    target = db.get_user(_try_int(m.text))
    if not target:
        await m.answer("Участник не найден. Пришлите ID:")
        return
    await _set_ban(target["id"], True, m.from_user.id)
    services.log(m.from_user.id, "ban", str(target["id"]))
    await services.notify(target["id"], "🚫 Вы заблокированы в боте.")
    for g in db.query("SELECT * FROM groups"):
        try:
            member = await m.bot.get_chat_member(g["chat_id"], target["id"])
            if member.status in ("member", "restricted"):
                await m.bot.ban_chat_member(g["chat_id"], target["id"])
                await m.bot.unban_chat_member(g["chat_id"], target["id"])
                await m.answer(f"🚫 Участник исключён из чата {g['chat_id']}.")
                break
        except Exception:
            continue
    await state.clear()
    await m.answer("✅ Заблокирован.", reply_markup=keyboards.main_menu(u))


def _try_int(s):
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return None


@router.callback_query(F.data.startswith("unban:new"))
async def unban_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "bans"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(BanUser.action)
    await c.message.answer("♻️ Пришлите ID для разбана:")
    await c.answer()


@router.message(BanUser.action, F.text)
async def unban_uid(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not db.has_right(u, "bans"):
        return
    target = db.get_user(_try_int(m.text))
    if not target:
        await m.answer("Участник не найден. Пришлите ID:")
        return
    await _set_ban(target["id"], False, m.from_user.id)
    services.log(m.from_user.id, "unban", str(target["id"]))
    await services.notify(target["id"], "♻️ Вы разблокированы! /start")
    await state.clear()
    await m.answer("✅ Разблокирован.", reply_markup=keyboards.main_menu(u))


async def templates_menu(c):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "templates"):
        await c.answer("Нет прав", show_alert=True)
        return
    tpls = db.query("SELECT * FROM templates ORDER BY id DESC LIMIT 20")
    rows = [[f"📑 {t['title'][:35]}", f"tplv:{t['id']}"] for t in tpls]
    rows.append(["➕ Создать шаблон", "tpl:new"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("📑 Шаблоны заданий:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("tplv:"))
async def tpl_view(c: CallbackQuery):
    tid = int(c.data.split(":")[1])
    t = db.get("SELECT * FROM templates WHERE id=?", (tid,))
    if not t:
        await c.answer("Не найдено", show_alert=True)
        return
    from handlers.tasks import POS_FILTERS
    await send_content(c.bot, c.from_user.id,
                       f"📑 Шаблон «{t['title']}»\nДля: "
                       f"{dict(POS_FILTERS).get(t['pos'], 'всех')}\n\n{t['text']}",
                       t["photo"],
                       kb([["🗑 Удалить", f"tpldel:{tid}"]]))
    await c.answer()


@router.callback_query(F.data.startswith("tpldel:"))
async def tpl_del(c: CallbackQuery):
    tid = int(c.data.split(":")[1])
    db.take_to_trash("templates", tid)
    db.execute("DELETE FROM templates WHERE id=?", (tid,))
    services.log(c.from_user.id, "template_del", str(tid))
    await c.answer("Удалено")


@router.callback_query(F.data.startswith("tpl:new"))
async def tpl_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "templates"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(TemplateCreate.title)
    await c.message.answer("📝 Название шаблона:")
    await c.answer()


@router.message(TemplateCreate.title, F.text)
async def tpl_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(TemplateCreate.text)
    await m.answer("📝 Текст задания в шаблоне:")


@router.message(TemplateCreate.text, F.text)
async def tpl_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(TemplateCreate.pos)
    from handlers.tasks import POS_FILTERS
    rows = [[name, f"tplp:{key}"] for key, name in POS_FILTERS]
    await m.answer("👔 Для какой должности?", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("tplp:"))
async def tpl_pos(c: CallbackQuery, state: FSMContext):
    await state.update_data(pos=c.data.split(":")[1])
    await state.set_state(TemplateCreate.photo)
    await c.message.answer("📷 Пришлите фото приложения (или напишите «нет»):")


@router.message(TemplateCreate.photo, F.photo)
async def tpl_photo(m: Message, state: FSMContext):
    await state.update_data(photo=m.photo[-1].file_id)
    await tpl_save(m, state)


@router.message(TemplateCreate.photo, F.text == "нет")
async def tpl_nophoto(m: Message, state: FSMContext):
    await state.update_data(photo=None)
    await tpl_save(m, state)


async def tpl_save(m: Message, state: FSMContext):
    data = await state.get_data()
    u = db.get_user(m.from_user.id)
    tid = db.execute(
        "INSERT INTO templates(title,text,pos,photo,created_at,created_by) "
        "VALUES(?,?,?,?,?,?)",
        (data["title"], data["text"], data["pos"], data.get("photo"), db.now(), u["id"]))
    services.log(u["id"], "template_new", str(tid))
    await state.clear()
    await m.answer(f"✅ Шаблон «{data['title']}» сохранён.",
                   reply_markup=keyboards.main_menu(u))


async def forms_menu(c):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "tasks"):
        await c.answer("Нет прав", show_alert=True)
        return
    forms = db.query("SELECT * FROM forms ORDER BY id DESC LIMIT 20")
    rows = [[f"📄 {f['title']}", f"formv:{f['id']}"] for f in forms]
    rows.append(["➕ Создать форму", "form:new"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("📄 Формы выполнения:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("formv:"))
async def form_view(c: CallbackQuery):
    fid = int(c.data.split(":")[1])
    f = db.get("SELECT * FROM forms WHERE id=?", (fid,))
    if not f:
        await c.answer("Не найдено", show_alert=True)
        return
    fields = db.jload(f["fields"])
    text = (f"📄 Форма «{f['title']}»\n\n" +
            "\n".join(f"{i+1}. {q}" for i, q in enumerate(fields)))
    await c.message.answer(text, reply_markup=kb([["🗑 Удалить", f"formdel:{fid}"],
                                                  ["⬅️ Назад", "back:menu"]]))
    await c.answer()


@router.callback_query(F.data.startswith("formdel:"))
async def form_del(c: CallbackQuery):
    fid = int(c.data.split(":")[1])
    db.execute("DELETE FROM forms WHERE id=?", (fid,))
    services.log(c.from_user.id, "form_del", str(fid))
    await c.answer("Удалена")


@router.callback_query(F.data.startswith("form:new"))
async def form_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "tasks"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(FormCreate.title)
    await c.message.answer("📝 Название формы:")
    await c.answer()


@router.message(FormCreate.title, F.text)
async def form_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(FormCreate.fields)
    await m.answer("Перечислите вопросы формы, каждый с новой строки:")


@router.message(FormCreate.fields, F.text)
async def form_fields(m: Message, state: FSMContext):
    data = await state.get_data()
    fields = [l.strip() for l in m.text.split("\n") if l.strip()]
    u = db.get_user(m.from_user.id)
    fid = db.execute(
        "INSERT INTO forms(title,fields,created_by,created_at) VALUES(?,?,?,?)",
        (data["title"], json.dumps(fields, ensure_ascii=False), u["id"], db.now()))
    services.log(u["id"], "form_new", str(fid))
    await state.clear()
    await m.answer(f"✅ Форма «{data['title']}» создана ({len(fields)} вопросов).",
                   reply_markup=keyboards.main_menu(u))


@router.callback_query(F.data.startswith("cur:new"))
async def cur_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "curators"):
        await c.answer("Нет прав", show_alert=True)
        return
    members = db.query("SELECT * FROM users WHERE banned=0 AND leave_at IS NULL LIMIT 15")
    rows = [[f"{mm['name']} (id {mm['id']})", f"curu:{mm['id']}"] for mm in members]
    await c.message.answer("👤 Кто будет куратором?", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("cur:list"))
async def cur_list(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "curators"):
        await c.answer("Нет прав", show_alert=True)
        return
    curs = db.query("SELECT c.*, u.name FROM curators c JOIN users u ON u.id=c.user_id")
    rows = []
    for cu in curs:
        rows.append([f"🧑‍🏫 {cu['name']} — {config.POSITIONS.get(cu['pos'], '?')}",
                     f"curdel:{cu['id']}"])
    if not rows:
        await c.message.answer("Кураторов пока нет.")
    else:
        rows.append(["⬅️ Назад", "back:menu"])
        await c.message.answer("🧑‍🏫 Кураторы (нажмите, чтобы снять):",
                               reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("curdel:"))
async def cur_del(c: CallbackQuery):
    curid = int(c.data.split(":")[1])
    db.execute("DELETE FROM curators WHERE id=?", (curid,))
    services.log(c.from_user.id, "curator_del", str(curid))
    await c.answer("Куратор снят")
    await cur_list(c)


@router.callback_query(F.data.startswith("curu:"))
async def cur_user(c: CallbackQuery, state: FSMContext):
    uid = int(c.data.split(":")[1])
    rows = [[name, f"curp:{uid}:{key}"] for key, name in config.POSITIONS.items()]
    await c.message.answer("👔 За какой должностью закрепить?", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("curp:"))
async def cur_pos(c: CallbackQuery):
    _, uid_s, pos = c.data.split(":")
    uid = int(uid_s)
    db.execute("DELETE FROM curators WHERE user_id=? AND pos=?", (uid, pos))
    db.execute("INSERT INTO curators(user_id,pos) VALUES(?,?)", (uid, pos))
    services.log(c.from_user.id, "curator_add", f"{uid} {pos}")
    await services.notify(uid, f"🧑‍🏫 Вы назначены куратором должности "
                               f"{config.POSITIONS.get(pos, pos)}!")
    u = db.get_user(c.from_user.id)
    await c.message.answer("✅ Куратор назначен.", reply_markup=keyboards.main_menu(u))
    await c.answer()


@router.callback_query(F.data.startswith("ow:"))
async def owner_dispatch(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not u or u["role"] < 4:
        await c.answer("Нет прав", show_alert=True)
        return
    key = c.data.split(":")[1]
    if key == "passwords":
        rows = [["👁 Участник", "pwget:pw_user"], ["👁 Админ", "pwget:pw_admin"],
                ["👁 Владелец", "pwget:pw_owner"],
                ["✏️ Изменить пароль", "pwset"], ["⬅️ Назад", "back:menu"]]
        await c.message.answer("🔐 Пароли:", reply_markup=kb(rows))
    elif key == "rights":
        admins = db.query("SELECT * FROM users WHERE role>=1 AND role<4 AND "
                          "leave_at IS NULL")
        rows = [[f"{a['name']} ({config.ROLE_NAMES[a['role']]})",
                 f"rt:sel:{a['id']}"] for a in admins]
        rows.append(["⬅️ Назад", "back:menu"])
        await c.message.answer("👥 Права админов (выберите):", reply_markup=kb(rows))
    elif key == "roles":
        await state.set_state(RoleGrant.user)
        await c.message.answer("👑 Пришлите ID участника, которому выдать роль:")
    elif key == "delete":
        await state.set_state(DeleteUser.user)
        await c.message.answer("🗑 Пришлите ID участника для полного удаления "
                               "(необратимо!):")
    elif key == "tz":
        users = db.query("SELECT * FROM users WHERE leave_at IS NULL LIMIT 15")
        rows = [[f"{x['name']}: {x['timezone']}", f"tzu:{x['id']}"] for x in users]
        rows.append(["⬅️ Назад", "back:menu"])
        await c.message.answer("🌍 Часовые пояса (нажмите, чтобы изменить):",
                               reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("pwget:"))
async def pw_get(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if u["role"] < 4:
        await c.answer()
        return
    key = c.data.split(":")[1]
    pw = db.setting(key, config.DEFAULT_PASSWORDS[key])
    await c.message.answer(f"🔑 Пароль («{key}»): {pw}\n(виден только владельцу)")
    await c.answer()


@router.callback_query(F.data.startswith("pwset"))
async def pw_set(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if u["role"] < 4:
        await c.answer()
        return
    await state.set_state(PasswordChange.key)
    rows = [["Участник", "pwk:pw_user"], ["Админ", "pwk:pw_admin"],
            ["Владелец", "pwk:pw_owner"]]
    await c.message.answer("✏️ Какой пароль меняем?", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("pwk:"))
async def pw_key(c: CallbackQuery, state: FSMContext):
    await state.update_data(key=c.data.split(":")[1])
    await state.set_state(PasswordChange.value)
    await c.message.answer("🔑 Пришлите новый пароль (минимум 6 символов, "
                           "не совпадающий с другими):")
    await c.answer()


@router.message(PasswordChange.value, F.text)
async def pw_value(m: Message, state: FSMContext):
    data = await state.get_data()
    ex_rk = keyboards.main_menu(db.get_user(m.from_user.id))
    if len(m.text.strip()) < 6:
        await m.answer("Слишком коротко (минимум 6 символов). Пришлите другой:")
        return
    others = [k for k in config.DEFAULT_PASSWORDS if k != data["key"]]
    vals = [db.setting(k, config.DEFAULT_PASSWORDS[k]) for k in others]
    if m.text.strip() in vals:
        await m.answer("Пароль совпадает с другим. Придумайте другой:")
        return
    db.set_setting(data["key"], m.text.strip())
    await state.clear()
    await m.answer("✅ Пароль обновлён.", reply_markup=ex_rk)
    services.log(m.from_user.id, "password_change", data["key"])


@router.callback_query(F.data.startswith("rt:sel:"))
async def rights_sel(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if u["role"] < 4:
        await c.answer()
        return
    uid = int(c.data.split(":")[2])
    target = db.get_user(uid)
    have = set(db.rights_of(target))
    rows = []
    for key, name in config.RIGHTS:
        rows.append([f"{'✅' if key in have else '❌'} {name}", f"rt:tgl:{uid}:{key}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer(f"👥 Права {target['name']} (нажмите, чтобы переключить):",
                           reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("rt:tgl:"))
async def rights_toggle(c: CallbackQuery):
    _, _, uid_s, key = c.data.split(":")
    uid = int(uid_s)
    target = db.get_user(uid)
    have = db.rights_of(target)
    if key in have:
        have.remove(key)
    else:
        have.append(key)
    db.execute("UPDATE users SET rights=? WHERE id=?",
               (json.dumps(have, ensure_ascii=False), uid))
    await c.answer("Изменено")
    await rights_sel(c)


@router.callback_query(F.data.startswith("tzu:"))
async def tz_edit(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if u["role"] < 4:
        await c.answer()
        return
    uid = int(c.data.split(":")[1])
    rows = [["Europe/Moscow", f"tzset:{uid}:Europe/Moscow"],
            ["Europe/Kaliningrad", f"tzset:{uid}:Europe/Kaliningrad"],
            ["Europe/Samara", f"tzset:{uid}:Europe/Samara"],
            ["Europe/Ulyanovsk", f"tzset:{uid}:Europe/Ulyanovsk"],
            ["Asia/Yekaterinburg", f"tzset:{uid}:Asia/Yekaterinburg"],
            ["Asia/Novosibirsk", f"tzset:{uid}:Asia/Novosibirsk"],
            ["Asia/Krasnoyarsk", f"tzset:{uid}:Asia/Krasnoyarsk"],
            ["Asia/Irkutsk", f"tzset:{uid}:Asia/Irkutsk"],
            ["Asia/Yakutsk", f"tzset:{uid}:Asia/Yakutsk"],
            ["Asia/Vladivostok", f"tzset:{uid}:Asia/Vladivostok"]]
    await c.message.answer("🌍 Выберите часовой пояс:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("tzset:"))
async def tz_set(c: CallbackQuery):
    _, uid_s, tz = c.data.split(":", 2)
    uid = int(uid_s)
    db.execute("UPDATE users SET timezone=? WHERE id=?", (tz, uid))
    target = db.get_user(uid)
    await services.notify(uid, f"🌍 Ваш часовой пояс обновлён: {tz}")
    await c.message.answer(f"✅ {fmt_name(target)}: {tz}")
    await c.answer()


@router.message(RoleGrant.user, F.text)
async def role_user(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    target = db.get_user(_try_int(m.text))
    if not target:
        await m.answer("Участник не найден. Пришлите ID:")
        return
    await state.update_data(user=target["id"])
    await state.set_state(RoleGrant.level)
    rows = [["Средний админ (уровень 2)", "rl:2"], ["Старший админ (уровень 3)", "rl:3"]]
    await m.answer(f"👑 Участник: {user_line(target)}. Какой уровень?" ,
                   reply_markup=kb(rows))


@router.callback_query(F.data.startswith("rl:"))
async def role_level(c: CallbackQuery, state: FSMContext):
    level = int(c.data.split(":")[1])
    data = await state.get_data()
    uid = data["user"]
    rights = config.DEFAULT_RIGHTS[level]
    db.execute("UPDATE users SET role=?, admin_level=?, rights=? WHERE id=?",
               (level, level, json.dumps(rights), uid))
    services.log(c.from_user.id, "role_grant", f"{uid} -> level {level}")
    await services.notify(uid, f"👑 Вам присвоена роль: {config.ROLE_NAMES[level]}")
    await state.clear()
    u = db.get_user(c.from_user.id)
    await c.message.answer("✅ Роль выдана.", reply_markup=keyboards.main_menu(u))
    await c.answer()


@router.message(DeleteUser.user, F.text)
async def del_user(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not db.has_right(u, "delete_users"):
        await m.answer("Нет прав")
        return
    target = db.get_user(_try_int(m.text))
    if not target:
        await m.answer("Участник не найден. Пришлите ID:")
        return
    if target["role"] >= 4:
        await m.answer("❌ Нельзя удалить владельца.")
        return
    await state.set_state(DeleteUser.confirm)
    await state.update_data(user=target["id"])
    works_cnt = db.get("SELECT COUNT(*) c FROM works WHERE user_id=?",
                       (target["id"],))["c"]
    await m.answer(f"⚠️ Будет удалено безвозвратно:\n{user_line(target)}\n"
                   f"{works_cnt} работ, все баллы, наказания, статусы, история.\n\n"
                   f"Для подтверждения введите кодовое слово: УДАЛИТЬ",
                   reply_markup=keyboards.rkb([["❌ Отмена"]]))


@router.message(DeleteUser.confirm, F.text)
async def del_confirm(m: Message, state: FSMContext):
    data = await state.get_data()
    u = db.get_user(m.from_user.id)
    if m.text.strip() != "УДАЛИТЬ":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=keyboards.main_menu(u))
        return
    uid = data["user"]
    target = db.get_user(uid)
    db.execute("DELETE FROM works WHERE user_id=?", (uid,))
    db.execute("DELETE FROM punishments WHERE user_id=?", (uid,))
    db.execute("DELETE FROM vote_records WHERE voter_id=?", (uid,))
    db.execute("DELETE FROM checklist_assignments WHERE user_id=?", (uid,))
    db.execute("UPDATE checklist_items SET taker_id=NULL, assigned_to=NULL "
               "WHERE taker_id=? OR assigned_to=?", (uid, uid))
    db.execute("DELETE FROM logs WHERE user_id=?", (uid,))
    db.execute("DELETE FROM curators WHERE user_id=?", (uid,))
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    services.log(m.from_user.id, "user_deleted", f"{uid} {fmt_name(target)}")
    cand = json.loads(db.setting("candidates", "[]"))
    if uid in cand:
        cand.remove(uid)
        db.set_setting("candidates", json.dumps(cand))
    await state.clear()
    await m.answer(f"🗑 Участник {uid} и все его данные удалены безвозвратно.",
                   reply_markup=keyboards.main_menu(u))
