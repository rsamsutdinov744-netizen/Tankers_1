import json
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton

import config
import database as db
import services
from states import PunishCreate, PunishReport, Reject
from utils import kb, file_list_from_message, send_content, fmt_name, parse_dt

router = Router()

REPORT_RK = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ Отправить"), KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True)

KIND_ROWS = [[name, f"pk:{key}"] for key, name in config.PUNISH_KINDS.items()]
ST_MAP = {"active": "🟠 Активно", "submitted": "⏳ На проверке", "rejected": "❌ Отклонено",
          "accepted": "✅ Принято", "closed": "⚫ Снято"}


@router.message(F.text == "⚖️ Наказания")
async def punish_list(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    rows = [["📤 Мои наказания", "p:mine"], ["⬅️ Назад", "back:menu"]]
    if db.has_right(u, "punishments"):
        rows.insert(0, ["➕ Выдать наказание", "p:new"])
        rows.insert(1, ["📋 Наказания участников", "p:all"])
    await m.answer("⚖️ Наказания:", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("p:mine"))
async def p_mine(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    rows_p = db.query("SELECT * FROM punishments WHERE user_id=? ORDER BY id DESC LIMIT 10",
                      (u["id"],))
    if not rows_p:
        await c.answer("Наказаний нет 🎉", show_alert=True)
        return
    lines = ["⚖️ Ваши наказания:\n"]
    rows = []
    for p in rows_p:
        lines.append(f"#{p['id']} {config.PUNISH_KINDS[p['kind']]} — {p['topic'] or ''}\n"
                     f"  Статус: {ST_MAP.get(p['status'], p['status'])}, "
                     f"срок: {(p['deadline'] or '—')[:10]}")
        if p["kind"] not in ("warning", "points") and p["status"] in ("active", "rejected"):
            rows.append(["📤 Сдать отчёт", f"preport:{p['id']}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("\n".join(lines), reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("preport:"))
async def preport(c: CallbackQuery, state: FSMContext):
    pid = int(c.data.split(":")[1])
    p = db.get("SELECT * FROM punishments WHERE id=?", (pid,))
    if not p or p["user_id"] != c.from_user.id:
        await c.answer("Нет доступа", show_alert=True)
        return
    if p["kind"] == "monthly":
        rows = db.query(
            "SELECT points, created_at FROM works WHERE user_id=? AND status='reviewed' "
            "AND created_at>=?", (p["user_id"],
            (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d %H:%M:%S")))
        real = round(sum(r["points"] for r in rows if r["points"] > 0), 1)
        points_weeks = [0.0, 0.0, 0.0, 0.0]
        now_ = datetime.now()
        for r in rows:
            if r["points"] <= 0:
                continue
            try:
                d = (now_ - datetime.strptime(r["created_at"][:19],
                                              "%Y-%m-%d %H:%M:%S")).days
            except Exception:
                continue
            w = min(3, d // 7)
            points_weeks[w] += r["points"]
        text = (f"📊 Отчёт за месяц — наказание #{pid}\n\n"
                f"Ваши данные за 4 недели (недели от свежей к старой):\n"
                f"• Неделя 1: {points_weeks[0]:.1f}\n"
                f"• Неделя 2: {points_weeks[1]:.1f}\n"
                f"• Неделя 3: {points_weeks[2]:.1f}\n"
                f"• Неделя 4: {points_weeks[3]:.1f}\n\n"
                f"Сложите числá и пришлите итог одним числом:")
        db.execute("UPDATE punishments SET data=? WHERE id=?",
                   (json.dumps({"real": real}), pid))
        await state.set_state(PunishReport.content)
        await state.update_data(pid=pid, files=[], text="", monthly=True,
                                real=real)
        await c.message.answer(text, reply_markup=REPORT_RK)
        await c.answer()
        return
    await state.set_state(PunishReport.content)
    await state.update_data(pid=pid, files=[], text="", monthly=False)
    await c.message.answer(f"📤 Отчёт по наказанию #{pid} «{p['topic'] or ''}».\n"
                           f"Пришлите текст, фото или файл (с источниками, "
                           f"если это поиск информации):", reply_markup=REPORT_RK)
    await c.answer()


@router.message(PunishReport.content, F.text == "❌ Отмена")
async def pr_cancel(m: Message, state: FSMContext):
    await state.clear()
    u = db.get_user(m.from_user.id)
    await m.answer("❌ Отменено", reply_markup=keyboards.main_menu(u))


def _parse_num(s):
    try:
        return float(s.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


@router.message(PunishReport.content)
async def pr_content(m: Message, state: FSMContext):
    data = await state.get_data()
    if m.text == "✅ Отправить":
        pid = data["pid"]
        text = data.get("text", "")
        files = data.get("files", [])
        if not text and not files:
            await m.answer("⚠️ Добавьте содержание отчёта.")
            return
        p = db.get("SELECT * FROM punishments WHERE id=?", (pid,))
        if data.get("monthly"):
            user_val = _parse_num(text)
            real = data.get("real", 0)
            if user_val is None or abs(user_val - real) >= 0.05:
                await m.answer(f"❌ Неверно ({user_val}). Пересчитайте и пришлите итог "
                               f"снова (одним числом):")
                services.log(m.from_user.id, "monthly_fail", f"{pid}: {user_val}≠{real}")
                return
            await state.update_data(monthly=False)
            text = f"Итог за месяц: {text} (проверено ботом ✅)"
        db.execute("UPDATE punishments SET status='submitted', submitted_at=?, result_text=?, "
                   "result_photo=? WHERE id=?",
                   (db.now(), text, files[0]["id"] if files and
                    files[0]["type"] == "photo" else None, pid))
        u = db.get_user(m.from_user.id)
        notif = (f"📤 Отчёт по наказанию #{pid} ({config.PUNISH_KINDS[p['kind']]})\n"
                 f"От: {u['name']} (id {u['id']})\n{p['topic'] or ''}\n\n{text}")
        await state.clear()
        for aid in {p["assigned_by"], *services.owners_ids()}:
            if aid != u["id"]:
                await send_content(services.get_bot(), aid, notif, None, files,
                                   kb([["✅ Принять", f"pcheck:{pid}:yes"],
                                       ["❌ Отклонить", f"pcheck:{pid}:no"]]))
        await m.answer("✅ Отчёт отправлен на проверку!",
                       reply_markup=keyboards.main_menu(u))
        services.log(u["id"], "punish_report", str(pid))
        return
    files = data.get("files", [])
    nf = file_list_from_message(m)
    if nf:
        files.extend(nf)
    text = (data.get("text", "") + ("\n" if data.get("text") and (m.text or m.caption) else "")
            + (m.text or m.caption or ""))
    await state.update_data(files=files, text=text)
    await m.answer("✅ Принято. Можно дополнить или нажать «✅ Отправить».")


@router.callback_query(F.data.startswith("pcheck:"))
async def p_check(c: CallbackQuery, state: FSMContext):
    _, pid_s, choice = c.data.split(":")
    pid = int(pid_s)
    p = db.get("SELECT * FROM punishments WHERE id=?", (pid,))
    if not p or p["status"] != "submitted":
        await c.answer("Недоступно", show_alert=True)
        return
    if choice == "yes":
        db.execute("UPDATE punishments SET status='accepted', checked_by=? WHERE id=?",
                   (c.from_user.id, pid))
        await services.notify(p["user_id"], f"✅ Отчёт по наказанию #{pid} принят!")
        if p["kind"] == "points":
            n = _parse_num(p["topic"] or "0")
            if n:
                await services.add_points(p["user_id"], -n, f"наказание #{pid}")
        services.log(c.from_user.id, "punish_accept", str(pid))
        try:
            await c.message.edit_text((c.message.text or "") + "\n\n✅ Принято.")
        except Exception:
            pass
    else:
        await state.set_state(Reject.reason)
        await state.update_data(pcheck_pid=pid)
        await c.message.answer("❌ Причина отклонения:")
    await c.answer()


@router.message(Reject.reason, F.text)
async def reject_reason(m: Message, state: FSMContext):
    data = await state.get_data()
    pid = data.get("pcheck_pid")
    if pid:
        p = db.get("SELECT * FROM punishments WHERE id=?", (pid,))
        db.execute("UPDATE punishments SET status='rejected', checked_by=?, check_comment=? "
                   "WHERE id=?", (m.from_user.id, m.text, pid))
        await services.notify(p["user_id"],
                              f"❌ Отчёт по наказанию #{pid} отклонён.\n"
                              f"Причина: {m.text}\nПеределайте и сдайте снова.")
        services.log(m.from_user.id, "punish_reject", str(pid))
    await state.clear()
    await m.answer("✅ Отклонено, участник уведомлён.",
                   reply_markup=keyboards.main_menu(db.get_user(m.from_user.id)))


@router.callback_query(F.data.startswith("p:all"))
async def p_all(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "punishments"):
        await c.answer("Нет прав", show_alert=True)
        return
    rows_p = db.query(
        "SELECT * FROM punishments WHERE status IN ('active','submitted','rejected') "
        "ORDER BY id DESC LIMIT 20")
    if not rows_p:
        await c.answer("Активных наказаний нет", show_alert=True)
        return
    st_map = {"active": "🟠", "submitted": "⏳", "rejected": "❌"}
    rows = []
    for p in rows_p:
        uu = db.get_user(p["user_id"])
        rows.append([f"#{p['id']} {st_map.get(p['status'],'')} "
                     f"{config.PUNISH_KINDS[p['kind']][:20]} — {fmt_name(uu)}",
                     f"p:view:{p['id']}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("📋 Наказания участников:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("p:view:"))
async def p_view(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    p = db.get("SELECT * FROM punishments WHERE id=?", (pid,))
    if not p:
        await c.answer("Не найдено", show_alert=True)
        return
    uu = db.get_user(p["user_id"])
    by = db.get_user(p["assigned_by"])
    text = (f"⚖️ Наказание #{pid}\nКому: {fmt_name(uu)} (id {uu['id']})\n"
            f"Тип: {config.PUNISH_KINDS[p['kind']]}\nТема: {p['topic'] or '—'}\n"
            f"Срок: {(p['deadline'] or '—')[:10]}\n"
            f"Выдал: {fmt_name(by)}\nСтатус: {ST_MAP.get(p['status'], p['status'])}\n"
            f"Отчёт: {p['result_text'] or '—'}")
    rows = []
    if p["status"] == "submitted":
        rows += [["✅ Принять", f"pcheck:{pid}:yes"], ["❌ Отклонить", f"pcheck:{pid}:no"]]
    rows.append(["🗑 Снять наказание", f"p:cancel:{pid}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await send_content(c.bot, c.from_user.id, text, p["result_photo"], None, kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("p:cancel:"))
async def p_cancel(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    p = db.get("SELECT * FROM punishments WHERE id=?", (pid,))
    if not p:
        await c.answer("Не найдено", show_alert=True)
        return
    db.execute("UPDATE punishments SET status='closed' WHERE id=?", (pid,))
    await services.notify(p["user_id"], f"😊 Наказание #{pid} снято.")
    services.log(c.from_user.id, "punish_cancel", str(pid))
    await c.answer("Наказание снято")


@router.callback_query(F.data.startswith("p:new"))
async def p_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "punishments"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(PunishCreate.user)
    members = db.query(
        "SELECT * FROM users WHERE banned=0 AND leave_at IS NULL ORDER BY name LIMIT 20")
    rows = [[f"{mm['name']} (id {mm['id']})", f"pu:{mm['id']}"] for mm in members]
    rows.append(["⬅️ Отмена", "back:menu"])
    await c.message.answer("👤 Кому наказание?", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("pu:"))
async def pu_user(c: CallbackQuery, state: FSMContext):
    uid = int(c.data.split(":")[1])
    await state.update_data(user=uid)
    await state.set_state(PunishCreate.kind)
    rows = KIND_ROWS + [["⬅️ Отмена", "back:menu"]]
    await c.message.answer("⚖️ Тип наказания:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("pk:"))
async def pu_kind(c: CallbackQuery, state: FSMContext):
    kind = c.data.split(":")[1]
    prompts = {
        "points": "➖ Сколько баллов снять (числом):",
        "monthly": "📊 Подтвердите создание отчёта за месяц — напишите «ок»:",
        "warning": "⚠️ Тема/причина предупреждения:",
        "search": "🔎 Что найти? Тема поиска:",
        "custom": "✏️ Опишите задание:",
    }
    await state.update_data(kind=kind)
    await state.set_state(PunishCreate.params)
    await c.message.answer(prompts[kind])
    await c.answer()


@router.message(PunishCreate.params, F.text)
async def pu_params(m: Message, state: FSMContext):
    data = await state.get_data()
    kind = data["kind"]
    if kind == "monthly" and m.text.lower() not in ("ок", "ok"):
        kind = data["kind"] = "custom"
    uid = data["user"]
    if kind in ("monthly", "search", "custom"):
        deadline = (datetime.now() + timedelta(days=config.PUNISH_GRACE_DAYS)).strftime(
            "%Y-%m-%d %H:%M:%S")
    else:
        deadline = None
    topic = "отчёт за месяц" if kind == "monthly" else m.text
    pid = db.execute(
        "INSERT INTO punishments(user_id,kind,topic,data,deadline,status,assigned_by,"
        "created_at) VALUES(?,?,?,?,?,?,?,?)",
        (uid, kind, topic, None, deadline, "active", m.from_user.id, db.now()))
    if kind == "points":
        n = _parse_num(m.text)
        if n:
            await services.add_points(uid, -n, f"наказание #{pid}")
        db.execute("UPDATE punishments SET status='accepted' WHERE id=?", (pid,))
    p = db.get("SELECT * FROM punishments WHERE id=?", (pid,))
    uu = db.get_user(uid)
    await state.clear()
    text = (f"⚖️ Вам выдано наказание #{pid}: {config.PUNISH_KINDS[kind]}\n"
            f"Тема: {topic}")
    if deadline:
        text += (f"\nСрок: до {deadline[:10]} "
                 f"(после +{config.PUNISH_GRACE_DAYS} дн. штраф "
                 f"−{config.PUNISH_FINE_PER_DAY} баллов/день)")
    has_report = kind in ("monthly", "search", "custom")
    await services.notify(uid, text,
                          kbd=kb([["📤 Сдать отчёт", f"preport:{pid}"]]) if has_report else None)
    services.log(m.from_user.id, "punish_new", f"{pid} user {uid}")
    await m.answer(f"✅ Наказание #{pid} выдано.", reply_markup=keyboards.main_menu(
        db.get_user(m.from_user.id)))
