import json
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import config
import database as db
import services
from states import ReminderCreate
from utils import kb, parse_dt, parse_time, fmt_name

router = Router()

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@router.message(F.text == "⏰ Напоминания")
async def reminders_menu(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    rows = [["⬅️ Назад", "back:menu"]]
    if db.has_right(u, "reminders"):
        rows.insert(0, ["➕ Создать напоминание", "rem:new"])
        rows.insert(1, ["📜 Активные", "rem:list"])
    await m.answer("⏰ Напоминания:", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("rem:new"))
async def rem_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "reminders"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(ReminderCreate.text)
    await c.message.answer("📝 Текст напоминания (или фото с подписью):")
    await c.answer()


@router.message(ReminderCreate.text, F.photo)
async def rem_text_photo(m: Message, state: FSMContext):
    await state.update_data(text=m.caption or "", photo=m.photo[-1].file_id)
    await rem_target_ask(m, state)


@router.message(ReminderCreate.text, F.text)
async def rem_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text, photo=None)
    await rem_target_ask(m, state)


@router.message(ReminderCreate.text)
async def rem_text_other(m: Message, state: FSMContext):
    await m.answer("Пришлите текст или фото с подписью.")


async def rem_target_ask(m: Message, state: FSMContext):
    await state.set_state(ReminderCreate.target)
    rows = [
        ["👥 Всем участникам", "remt:all"],
        ["👤 Одному", "remt:one"],
        ["✌️ Нескольким", "remt:some"],
        ["📢 В чаты (место публикации)", "remt:chats"],
    ]
    await m.answer("👥 Кому напоминание?", reply_markup=kb(rows))


async def _pick_users(c, state, multi):
    members = db.query(
        "SELECT * FROM users WHERE banned=0 AND leave_at IS NULL ORDER BY id LIMIT 15")
    rows = [[f"{mm['name']} (id {mm['id']})", f"remu:{mm['id']}"] for mm in members]
    if multi:
        rows.append(["✅ Готово", "remu:done"])
        await state.update_data(picked=[])
    await c.message.answer("✌️ Выберите участников:" if multi else "👤 Кому?",
                           reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("remt:one"))
async def remt_one(c: CallbackQuery, state: FSMContext):
    await _pick_users(c, state, multi=False)


@router.callback_query(F.data.startswith("remt:some"))
async def remt_some(c: CallbackQuery, state: FSMContext):
    await _pick_users(c, state, multi=True)


@router.callback_query(F.data.startswith("remu:"))
async def remu_pick(c: CallbackQuery, state: FSMContext):
    val = c.data.split(":")[1]
    data = await state.get_data()
    if val == "done":
        picked = data.get("picked", [])
        if not picked:
            await c.answer("Никого не выбрано", show_alert=True)
            return
        await state.update_data(target="some")
        await rem_mode_ask(c.message, state)
        await c.answer()
        return
    if data.get("picked") is not None:
        picked = data["picked"]
        if int(val) not in picked:
            picked.append(int(val))
        await state.update_data(picked=picked, target="some")
        names = ", ".join(fmt_name(db.get_user(p)) or str(p) for p in picked)
        await c.message.answer(f"✅ Выбрано ({len(picked)}): {names}")
    else:
        await state.update_data(target="one", picked=[int(val)])
        await rem_mode_ask(c.message, state)
    await c.answer()


@router.callback_query(F.data.startswith("remt:all"))
async def remt_all(c: CallbackQuery, state: FSMContext):
    await state.update_data(target="all")
    await rem_mode_ask(c.message, state)
    await c.answer()


@router.callback_query(F.data.startswith("remt:chats"))
async def remt_chats(c: CallbackQuery, state: FSMContext):
    await state.update_data(target="chats")
    await rem_mode_ask(c.message, state)
    await c.answer()


async def rem_mode_ask(message: Message, state: FSMContext):
    await state.set_state(ReminderCreate.mode)
    rows = [
        ["1️⃣ Один раз", "remm:once"],
        ["🔁 Каждую неделю", "remm:weekly"],
        ["📅 По датам", "remm:dates"],
    ]
    await message.answer("⏱️ Когда напомнить?", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("remm:"))
async def remm_mode(c: CallbackQuery, state: FSMContext):
    mode = c.data.split(":")[1]
    await state.update_data(mode=mode)
    if mode == "once":
        await state.set_state(ReminderCreate.datetime_in)
        await c.message.answer("📅 Дата и время в формате ДД.ММ.ГГГГ ЧЧ:ММ "
                               "(время — московское):")
    elif mode == "weekly":
        rows = [[WEEKDAYS[i], f"remd:{i+1}"] for i in range(7)]
        rows.append(["✅ Готово", "remd:done"])
        await state.update_data(days=[])
        await state.set_state(ReminderCreate.weekly)
        await c.message.answer("🔁 Выберите дни недели:", reply_markup=kb(rows))
    else:
        await state.set_state(ReminderCreate.dates)
        await c.message.answer("📅 Перечислите даты через запятую (ДД.ММ.ГГГГ):")
    await c.answer()


@router.message(ReminderCreate.datetime_in, F.text)
async def rem_once(m: Message, state: FSMContext):
    dt = parse_dt(m.text)
    if not dt:
        await m.answer("Не понял дату. Пример: 25.12.2025 18:00")
        return
    await state.update_data(dt_once=dt.strftime("%Y-%m-%d %H:%M:%S"))
    await rem_choose_time(m, state)


@router.message(ReminderCreate.weekly, F.text)
async def rem_week_done(m: Message, state: FSMContext):
    if m.text != "✅ Готово":
        return
    data = await state.get_data()
    if not data.get("days"):
        await m.answer("Выберите хотя бы один день!")
        return
    await rem_choose_time(m, state)


@router.callback_query(F.data.startswith("remd:"))
async def remd_pick(c: CallbackQuery, state: FSMContext):
    val = c.data.split(":")[1]
    if val == "done":
        data = await state.get_data()
        if not data.get("days"):
            await c.answer("Выберите хотя бы один день!", show_alert=True)
            return
        await rem_choose_time(c.message, state)
        await c.answer()
        return
    data = await state.get_data()
    days = data.get("days", [])
    if int(val) not in days:
        days.append(int(val))
        await state.update_data(days=days)
    await c.answer(f"✅ {WEEKDAYS[int(val)-1]}")


@router.message(ReminderCreate.dates, F.text)
async def rem_dates(m: Message, state: FSMContext):
    dates = []
    for part in m.text.replace(" ", "").split(","):
        dt = parse_dt(part, "%d.%m.%Y")
        if dt:
            dates.append(dt.strftime("%Y-%m-%d"))
    if not dates:
        await m.answer("Не нашёл дат. Пример: 01.12.2025, 15.12.2025")
        return
    await state.update_data(dates=dates)
    await rem_choose_time(m, state)


async def rem_choose_time(m: Message, state: FSMContext):
    data = await state.get_data()
    rows = [["⏰ Одно время для всех", "remtm:one"]]
    if data.get("target") in ("all", "some", "one"):
        rows.append(["🌍 Каждому по его часовому поясу", "remtm:tz"])
    await state.set_state(ReminderCreate.time_mode)
    await m.answer("⏰ Как задаём время?", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("remtm:one"))
async def remtm_one(c: CallbackQuery, state: FSMContext):
    await state.set_state(ReminderCreate.time_one)
    await state.update_data(tz_mode=False)
    await c.message.answer("⏰ Время в формате ЧЧ:ММ (московское):")
    await c.answer()


@router.callback_query(F.data.startswith("remtm:tz"))
async def remtm_tz(c: CallbackQuery, state: FSMContext):
    await state.set_state(ReminderCreate.time_one)
    await state.update_data(tz_mode=True)
    await c.message.answer("🌍 У каждого участника напоминание придёт, когда наступит "
                           "это время в его часовом поясе.\n⏰ Укажите время (ЧЧ:ММ):")
    await c.answer()


@router.message(ReminderCreate.time_one, F.text)
async def rem_time_one(m: Message, state: FSMContext):
    t = parse_time(m.text)
    if not t:
        await m.answer("Не понял время. Пример: 17:00")
        return
    await state.update_data(time=t)
    await rem_finalize(m, state)


async def rem_finalize(message: Message, state: FSMContext):
    data = await state.get_data()
    u = db.get_user(message.from_user.id)
    kind = data["mode"]
    dm_users = None
    time_s = data.get("time")
    if data.get("tz_mode"):
        if data.get("target") == "all":
            uid_list = [r["id"] for r in db.query(
                "SELECT id FROM users WHERE banned=0 AND leave_at IS NULL AND role=0")]
        else:
            uid_list = data.get("picked", [])
        dm_users = [{"uid": uid, "time": time_s,
                     "timezone": (db.get_user(uid) or {}).get("timezone", "Europe/Moscow")}
                    for uid in uid_list]
    rid = db.execute(
        "INSERT INTO reminders(text,kind,weekly,dates,time,fired,chat_id,thread,active,"
        "created_by,dm_users,created_at,photo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (data["text"], kind, json.dumps(data.get("days", [])),
         json.dumps(data.get("dates", [])),
         data.get("dt_once") if kind == "once" else time_s,
         0, None, None, 1, message.from_user.id,
         json.dumps(dm_users, ensure_ascii=False) if dm_users else None,
         db.now(), data.get("photo")))
    await state.clear()
    if kind == "once":
        desc = f"один раз {data.get('dt_once', '')} МСК"
    elif kind == "weekly":
        desc = "каждую неделю: " + ", ".join(WEEKDAYS[d - 1] for d in data.get("days", []))
    else:
        desc = "по датам: " + ", ".join(data.get("dates", []))
    text = (f"⏰ Напоминание #{rid} создано\nРасписание: {desc}"
            + (f"\nВремя: {time_s}" if time_s and kind != "once" else "")
            + f"\nПолучат: {data.get('target', 'chats')}"
            + ("\n(индивидуально по часовым поясам)" if dm_users else "")
            + f"\n\nТекст:\n{data['text']}")
    if not dm_users:
        await services.publish(services.get_bot(), "reminder",
                               f"⏰ Напоминание:\n{data['text']}", data.get("photo"),
                               warn=False)
    services.log(u["id"], "reminder_new", str(rid))
    await message.answer(text + "\n\n✅ Напоминание активно! /cancel — вернуться в меню")


@router.callback_query(F.data.startswith("rem:list"))
async def rem_list(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "reminders"):
        await c.answer("Нет прав", show_alert=True)
        return
    rows_r = db.query("SELECT * FROM reminders WHERE active=1 ORDER BY id DESC LIMIT 20")
    if not rows_r:
        await c.answer("Активных напоминаний нет", show_alert=True)
        return
    kbrows = [[f"#{r['id']} {r['text'][:35]}", f"remview:{r['id']}"] for r in rows_r]
    kbrows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("📜 Активные напоминания:", reply_markup=kb(kbrows))
    await c.answer()


@router.callback_query(F.data.startswith("remview:"))
async def rem_view(c: CallbackQuery):
    rid = int(c.data.split(":")[1])
    r = db.get("SELECT * FROM reminders WHERE id=?", (rid,))
    if not r:
        await c.answer("Не найдено", show_alert=True)
        return
    days = ", ".join(WEEKDAYS[d - 1] for d in db.jload(r["weekly"]) if 1 <= d <= 7)
    text = (f"⏰ Напоминание #{rid}\nТекст: {r['text']}\nТип: {r['kind']}\n"
            f"Время: {r['time'] or '—'}\nДни: {days or '—'}\n"
            f"Даты: {', '.join(db.jload(r['dates'])) or '—'}")
    await c.message.answer(text, reply_markup=kb([
        ["🗑 Удалить", f"remdel:{rid}"], ["⬅️ Назад", "rem:list"]]))
    await c.answer()


@router.callback_query(F.data.startswith("remdel:"))
async def rem_del(c: CallbackQuery):
    rid = int(c.data.split(":")[1])
    db.execute("DELETE FROM reminders WHERE id=?", (rid,))
    services.log(c.from_user.id, "reminder_del", str(rid))
    await c.answer("Удалено")
    try:
        await c.message.delete()
    except Exception:
        pass
