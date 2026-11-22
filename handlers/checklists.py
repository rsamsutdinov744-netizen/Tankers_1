import json
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton

import config
import database as db
import services
import keyboards
from states import ChecklistCreate, ChecklistProof
from utils import kb, file_list_from_message, send_content, fmt_name

router = Router()

SUBMIT_RK = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ Отправить"), KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True)

ITEM_STATUS = {"free": "⚪ свободен", "taken": "🟠 взят", "done": "🟠 на проверке",
               "checked": "✅ зачтён", "failed": "❌ не зачтён"}


def cl_menu_kb(u, cl_id):
    rows = [["✅ Мои чек-листы", "cl:my"], ["⬅️ Назад", "back:menu"]]
    if u["role"] >= 1 and db.has_right(u, "checklists"):
        rows.insert(0, ["➕ Создать чек-лист", "cl:new"])
    return kb(rows)


@router.message(F.text.in_(["✅ Чек-листы", "🗓 Чек-листы"]))
async def checklists_menu(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    active = db.query(
        "SELECT * FROM checklists WHERE status='active' ORDER BY id DESC")
    rows = []
    for cl in active:
        has_mine = db.get(
            "SELECT COUNT(*) c FROM checklist_items WHERE checklist_id=? AND "
            "(status='free' OR assigned_to=? AND status='free')",
            (cl["id"], u["id"]))["c"]
        mark = "🟢" if has_mine else "⚪"
        rows.append([f"{mark} {cl['title'][:40]}", f"cl:view:{cl['id']}"])
    if u["role"] >= 1 and db.has_right(u, "checklists"):
        rows.append(["➕ Создать чек-лист", "cl:new"])
    rows.append(["⬅️ Назад", "back:menu"])
    await m.answer("✅ Чек-листы (🟢 — есть свободные пункты):", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("cl:view:"))
async def cl_view(c: CallbackQuery, state: FSMContext):
    cl_id = int(c.data.split(":")[2])
    cl = db.get("SELECT * FROM checklists WHERE id=?", (cl_id,))
    if not cl:
        await c.answer("Не найдено", show_alert=True)
        return
    u = db.get_user(c.from_user.id)
    items = db.query("SELECT * FROM checklist_items WHERE checklist_id=?", (cl_id,))
    lines = [f"✅ Чек-лист #{cl['id']} «{cl['title']}»",
             f"Бонус за идеал: {cl['bonus']}",
             f"Срок: {(cl['deadline'] or '—')[:10]}", ""]
    rows = []
    for it in items:
        taker = db.get_user(it["taker_id"]) if it["taker_id"] else None
        extra = f" — {fmt_name(taker)}" if taker and taker["id"] != u["id"] else ""
        lines.append(f"• #{it['id']} {it['text'][:60]} — "
                     f"{ITEM_STATUS.get(it['status'], it['status'])}{extra}")
        if it["status"] == "free":
            rows.append([f"🖐 Взять: {it['text'][:28]}", f"clit:take:{it['id']}"])
    for it in items:
        if it["taker_id"] == u["id"] and it["status"] == "taken":
            rows.append([f"📤 Отметить: {it['text'][:28]}", f"clit:proof:{it['id']}"])
        if (it["taker_id"] == u["id"] and it["status"] == "checked" and
                not it["check_comment"]):
            pass
    if u["role"] >= 1 and any(it["status"] == "done" for it in items):
        rows.append(["🔎 Проверить пункты", f"cl:check:{cl_id}"])
    if u["role"] >= 1 and cl["status"] == "active":
        rows.append(["🗑 В корзину", f"cl:del:{cl_id}"])
    rows.append(["🔄 Обновить", f"cl:view:{cl_id}"])
    rows.append(["⬅️ Назад", "back:menu"])
    if c.message.photo or c.message.document:
        await c.message.answer("\n".join(lines), reply_markup=kb(rows))
    else:
        try:
            await c.message.edit_text("\n".join(lines), reply_markup=kb(rows))
        except Exception:
            await c.message.answer("\n".join(lines), reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("clit:take:"))
async def clit_take(c: CallbackQuery, state: FSMContext):
    it_id = int(c.data.split(":")[2])
    it = db.get("SELECT * FROM checklist_items WHERE id=?", (it_id,))
    if not it or it["status"] != "free":
        await c.answer("Пункт уже занят", show_alert=True)
        return
    u = db.get_user(c.from_user.id)
    mode = "together" if it["assigned_to"] and it["assigned_to"] != u["id"] else "alone"
    db.execute("UPDATE checklist_items SET status='taken', taker_id=?, taken_mode=? "
               "WHERE id=?", (u["id"], mode, it_id))
    services.log(u["id"], "cl_take", str(it_id))
    await state.set_state(ChecklistProof.content)
    await state.update_data(item_id=it_id, files=[], text="")
    await c.message.answer(f"🟠 Пункт ваш «{it['text'][:50]}». "
                           f"Пришлите подтверждение (текст, фото, файл):",
                           reply_markup=SUBMIT_RK)
    await c.answer()


@router.callback_query(F.data.startswith("clit:proof:"))
async def clit_proof(c: CallbackQuery, state: FSMContext):
    it_id = int(c.data.split(":")[2])
    await state.set_state(ChecklistProof.content)
    await state.update_data(item_id=it_id, files=[], text="")
    await c.message.answer("📎 Пришлите подтверждение выполнения:", reply_markup=SUBMIT_RK)
    await c.answer()


@router.message(ChecklistProof.content, F.text == "❌ Отмена")
async def clp_cancel(m: Message, state: FSMContext):
    await state.clear()
    u = db.get_user(m.from_user.id)
    await m.answer("❌ Отменено", reply_markup=keyboards.main_menu(u))


@router.message(ChecklistProof.content)
async def clp_content(m: Message, state: FSMContext):
    data = await state.get_data()
    if m.text == "✅ Отправить":
        text = data.get("text", "")
        files = data.get("files", [])
        if not text and not files:
            await m.answer("⚠️ Добавьте подтверждение (текст/фото/файл).")
            return
        it_id = data["item_id"]
        db.execute("UPDATE checklist_items SET status='done', proof_text=?, proof_files=? "
                   "WHERE id=?",
                   (text, json.dumps(files, ensure_ascii=False), it_id))
        it = db.get("SELECT * FROM checklist_items WHERE id=?", (it_id,))
        cl = db.get("SELECT * FROM checklists WHERE id=?", (it["checklist_id"],))
        u = db.get_user(m.from_user.id)
        notif = (f"📤 Пункт чек-листа #{it_id} «{cl['title']}» выполнен\n"
                 f"От: {u['name']} (id {u['id']})\nПункт: {it['text']}\n\n{text}")
        checker_id = cl["created_by"]
        await services.notify(checker_id, notif, files=files,
                              kbd=kb([["✅ Правильно", f"clchk:{it_id}:yes"],
                                      ["❌ Неправильно", f"clchk:{it_id}:no"]]))
        await state.clear()
        await m.answer("✅ Выполнение отправлено на проверку.",
                       reply_markup=keyboards.main_menu(u))
        services.log(u["id"], "cl_done", str(it_id))
        return
    files = data.get("files", [])
    nf = file_list_from_message(m)
    if nf:
        files.extend(nf)
    text = (data.get("text", "") + ("\n" if data.get("text") and (m.text or m.caption) else "")
            + (m.text or m.caption or ""))
    await state.update_data(files=files, text=text)
    await m.answer("✅ Принято. Можно дополнить или нажать «✅ Отправить».")


@router.callback_query(F.data.startswith("clchk:"))
async def cl_check_item(c: CallbackQuery):
    _, it_id_s, choice = c.data.split(":")
    it_id = int(it_id_s)
    it = db.get("SELECT * FROM checklist_items WHERE id=?", (it_id,))
    if not it or it["status"] != "done":
        await c.answer("Недоступно", show_alert=True)
        return
    cl = db.get("SELECT * FROM checklists WHERE id=?", (it["checklist_id"],))
    taker = db.get_user(it["taker_id"])
    per = 0.5 if it["taken_mode"] == "alone" else 0.4
    if choice == "yes":
        db.execute("UPDATE checklist_items SET status='checked', checked_by=?, checked_at=? "
                   "WHERE id=?", (c.from_user.id, db.now(), it_id))
        await services.add_points(taker["id"], per, f"пункт чек-листа #{it_id}")
        await services.notify(taker["id"],
                              f"✅ Пункт чек-листа зачтён: {it['text'][:50]} (+{per})")
    else:
        db.execute("UPDATE checklist_items SET status='failed', checked_by=?, checked_at=?, "
                   "check_comment='ложь' WHERE id=?", (c.from_user.id, db.now(), it_id))
        await services.add_points(taker["id"], -config.CHECKLIST_LIE_FINE,
                                  f"ложь в чек-листе #{it_id}")
        await services.notify(taker["id"],
                              f"❌ Пункт чек-листа не зачтён (ложь): "
                              f"−{config.CHECKLIST_LIE_FINE} баллов")
    services.log(c.from_user.id, "cl_check", f"{it_id} {choice}")
    remaining = db.get("SELECT COUNT(*) c FROM checklist_items WHERE checklist_id=? AND "
                       "status IN ('free','taken','done')", (it["checklist_id"],))["c"]
    if remaining == 0:
        bad = db.get("SELECT COUNT(*) c FROM checklist_items WHERE checklist_id=? AND "
                     "status='failed'", (it["checklist_id"],))["c"]
        participants = list({r["taker_id"] for r in db.query(
            "SELECT DISTINCT taker_id FROM checklist_items WHERE checklist_id=? AND "
            "taker_id IS NOT NULL", (it["checklist_id"],))})
        if bad == 0 and participants:
            for pid in participants:
                await services.add_points(pid, cl["bonus"] or 2, "идеальный чек-лист")
                await services.notify(pid, f"🌟 Идеальный чек-лист! "
                                           f"+{cl['bonus'] or 2} балла каждому.")
        db.execute("UPDATE checklists SET status='closed' WHERE id=?", (it["checklist_id"],))
        db.to_archive("checklists", it["checklist_id"])
        await services.publish(c.bot, "checklist", f"✅ Чек-лист «{cl['title']}» завершён.")
    await c.answer("Отмечено")


@router.callback_query(F.data.startswith("cl:new"))
async def cl_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not u or not db.has_right(u, "checklists"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(ChecklistCreate.title)
    await c.message.answer("📝 Название чек-листа:")
    await c.answer()


@router.message(ChecklistCreate.title, F.text)
async def cl_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(ChecklistCreate.deadline)
    await m.answer("⏰ Срок (ДД.ММ.ГГГГ) или «нет»:")


@router.message(ChecklistCreate.deadline, F.text)
async def cl_deadline(m: Message, state: FSMContext):
    from utils import parse_dt
    if m.text.lower() != "нет":
        dt = parse_dt(m.text)
        if not dt:
            await m.answer("Не понял дату. Пример: 25.12.2025 или «нет»:")
            return
        await state.update_data(deadline=dt.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        await state.update_data(deadline=None)
    await state.set_state(ChecklistCreate.bonus)
    await m.answer("🎁 Бонус за идеальное выполнение (по умолчанию 2):")


@router.message(ChecklistCreate.bonus, F.text)
async def cl_bonus(m: Message, state: FSMContext):
    try:
        bonus = float(m.text.replace(",", "."))
    except ValueError:
        bonus = 2.0
    await state.update_data(bonus=bonus, items=[])
    await state.set_state(ChecklistCreate.items)
    await m.answer("➕ Отправляйте пункты по одному. Когда закончите — напишите «готово»:",
                   reply_markup=keyboards.rkb([["готово"]]))


@router.message(ChecklistCreate.items, F.text)
async def cl_items(m: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get("items", [])
    if m.text.lower() == "готово":
        if not items:
            await m.answer("⚠️ Добавьте хотя бы один пункт:")
            return
        await state.update_data(items=items, assigns=[])
        await state.set_state(ChecklistCreate.assign)
        rows = [["👥 Назначить каждому", "classign:all"],
                ["🆓 Любой может взять", "classign:free"],
                ["👤 Назначить по одному", "classign:each"]]
        await m.answer("👥 Как назначаем пункты?", reply_markup=kb(rows))
        return
    items.append(m.text)
    await state.update_data(items=items)
    await m.answer(f"✅ Пункт {len(items)} добавлен. Ещё пункт или «готово»:")


@router.callback_query(F.data.startswith("classign:"))
async def cl_assign(c: CallbackQuery, state: FSMContext):
    mode = c.data.split(":")[1]
    await state.update_data(assign_mode=mode)
    if mode in ("all", "free"):
        await _save_checklist(c, state, assign_all=(mode == "all"))
        return
    members = db.query(
        "SELECT * FROM users WHERE role=0 AND banned=0 AND leave_at IS NULL")
    rows = [[f"{mm['name']} (id {mm['id']})", f"clitem_assign:{mm['id']}"]
            for mm in members[:15]]
    rows.append(["⬅️ Пропустить", "clitem_assign:skip"])
    await c.message.answer("👤 Выберите исполнителя пункта 1:", reply_markup=kb(rows))
    await c.answer()


async def _save_checklist(c: CallbackQuery, state: FSMContext, assign_all):
    data = await state.get_data()
    items = data["items"]
    cl_id = db.execute(
        "INSERT INTO checklists(title,status,created_by,deadline,bonus) VALUES(?,?,?,?,?)",
        (data["title"], "active", c.from_user.id, data.get("deadline"), data["bonus"]))
    for it in items:
        db.execute("INSERT INTO checklist_items(checklist_id,text,status) VALUES(?,?,'free')",
                   (cl_id, it))
    if assign_all:
        members = db.query(
            "SELECT id FROM users WHERE role=0 AND banned=0 AND leave_at IS NULL")
        for mem in members:
            db.execute(
                "INSERT INTO checklist_assignments(checklist_id,user_id) VALUES(?,?)",
                (cl_id, mem["id"]))
    await state.update_data(cl_id=cl_id)
    await state.set_state(ChecklistCreate.checker)
    rows = [["🧑‍💼 Проверяю сам", "clchecker:self"],
            ["👑 Владелец", "clchecker:owner"],
            ["👤 Назначить", "clchecker:assign"]]
    await c.message.answer(f"✅ Чек-лист #{cl_id} создан. Кто проверяет?",
                           reply_markup=kb(rows))


@router.message(ChecklistCreate.checker)
async def whatever(m: Message):
    pass


@router.callback_query(F.data.startswith("clitem_assign:"))
async def clitem_assign(c: CallbackQuery, state: FSMContext):
    val = c.data.split(":")[1]
    data = await state.get_data()
    assigns = data.get("assigns", [])
    items = data["items"]
    if val != "skip":
        assigns.append(int(val))
        await state.update_data(assigns=assigns)
    if len(assigns) >= len(items):
        await _save_checklist(c, state, assign_all=False)
        await c.answer()
        return
    members = db.query("SELECT * FROM users WHERE role=0 AND banned=0 AND leave_at IS NULL")
    rows = [[f"{mm['name']} (id {mm['id']})", f"clitem_assign:{mm['id']}"] for mm in members[:15]]
    rows.append(["⬅️ Пропустить", "clitem_assign:skip"])
    await c.message.answer(f"Пункт {len(assigns)+1}/{len(items)}: "
                           f"«{items[len(assigns)][:40]}» — кому назначить?",
                           reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("clchecker:"))
async def cl_checker(c: CallbackQuery, state: FSMContext):
    val = c.data.split(":")[1]
    data = await state.get_data()
    if val == "assign":
        members = db.query(
            "SELECT * FROM users WHERE banned=0 AND leave_at IS NULL")
        rows = [[f"{mm['name']} (id {mm['id']})", f"clchecker:{mm['id']}"]
                for mm in members[:15] if mm["id"] != c.from_user.id]
        await c.message.answer("👤 Выберите проверяющего:", reply_markup=kb(rows))
        await c.answer()
        return
    if val == "self":
        checker_id = c.from_user.id
    elif val == "owner":
        owners = services.owners_ids()
        checker_id = owners[0] if owners else c.from_user.id
    else:
        checker_id = int(val)
    db.execute("UPDATE checklists SET created_by=? WHERE id=?", (checker_id, data["cl_id"]))
    rows_items = db.query("SELECT * FROM checklist_items WHERE checklist_id=?", (data["cl_id"],))
    assigns = data.get("assigns", [])
    for i, it in enumerate(rows_items):
        if data.get("assign_mode") == "each" and i < len(assigns):
            db.execute("UPDATE checklist_items SET assigned_to=? WHERE id=?",
                       (assigns[i], it["id"]))
    services.log(c.from_user.id, "cl_create", str(data["cl_id"]))
    text = f"✅ Новый чек-лист «{data['title']}»\nОткройте и возьмите пункты."
    await services.publish(c.bot, "checklist", text,
                           kbd=kb([["👁 Открыть", f"cl:view:{data['cl_id']}"]]))
    await state.clear()
    await c.message.answer("✅ Чек-лист опубликован!",
                           reply_markup=keyboards.main_menu(db.get_user(c.from_user.id)))
    await c.answer()


@router.callback_query(F.data.startswith("cl:del:"))
async def cl_del(c: CallbackQuery):
    cl_id = int(c.data.split(":")[2])
    db.take_to_trash("checklists", cl_id)
    db.execute("UPDATE checklists SET status='deleted' WHERE id=?", (cl_id,))
    services.log(c.from_user.id, "cl_delete", str(cl_id))
    await c.message.answer("🗑 Чек-лист в корзине (48 ч на возврат).")
    await c.answer()


@router.callback_query(F.data.startswith("cl:check:"))
async def cl_check_menu(c: CallbackQuery):
    cl_id = int(c.data.split(":")[2])
    done_items = db.query(
        "SELECT * FROM checklist_items WHERE checklist_id=? AND status='done'", (cl_id,))
    if not done_items:
        await c.answer("Нет пунктов на проверку", show_alert=True)
        return
    rows = []
    for it in done_items:
        taker = db.get_user(it["taker_id"]) if it["taker_id"] else None
        rows.append([f"{'🥇' if it['taken_mode'] != 'together' else '🤝'} "
                     f"{it['text'][:35]} — {fmt_name(taker)}",
                     f"clchk_view:{it['id']}"])
    rows.append(["⬅️ Назад", f"cl:view:{cl_id}"])
    await c.message.answer("🔎 Проверка пунктов (нажмите, чтобы увидеть подтверждение):",
                           reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("clchk_view:"))
async def clchk_view(c: CallbackQuery):
    it_id = int(c.data.split(":")[1])
    it = db.get("SELECT * FROM checklist_items WHERE id=?", (it_id,))
    if not it:
        await c.answer("Не найдено", show_alert=True)
        return
    taker = db.get_user(it["taker_id"]) if it["taker_id"] else None
    text = (f"📸 Пункт #{it_id} от {fmt_name(taker)}\n{it['text']}\n\n"
            f"{it['proof_text'] or ''}")
    rows = [["✅ Правильно", f"clchk:{it_id}:yes"],
            ["❌ Неправильно", f"clchk:{it_id}:no"],
            ["⬅️ Назад", f"cl:check:{it['checklist_id']}"]]
    await send_content(c.bot, c.from_user.id, text, None,
                       db.jload(it["proof_files"]), kb(rows))
    await c.answer()
