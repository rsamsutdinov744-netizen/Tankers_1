from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import config
import database as db
import services
from states import TaskCreate, WorkSubmit, Grade, TemplateCreate, FormCreate
from utils import kb, send_content, file_list_from_message, extract_files, \
    SUPPORT_PHRASES, support_phrase, fmt_name

router = Router()

POS_FILTERS = [("all", "🌐 Общее"), ("artist", "🎨 Художник"), ("writer", "✍️ Сценарист"),
               ("animator", "🎬 Аниматор"), ("helper", "🧰 Помощник")]


def task_text(t, user=None):
    status_map = {"active": "🟢 Активно", "closed": "✅ Закрыто", "deleted": "🗑 Удалено"}
    u_done = ""
    if user:
        w = db.get("SELECT status FROM works WHERE task_id=? AND user_id=? AND "
                   "kind IN ('free','form') ORDER BY id DESC", (t["id"], user["id"]))
        if w:
            u_done = {"submitted": "\n📤 Ваша работа на проверке",
                      "reviewed": "\n✅ Ваша работа проверена",
                      "needs_correction": "\n✏️ Требуется корректировка"}.get(w["status"], "")
    dl = f"\n⏰ Срок: {t['deadline'][:16]}" if t.get("deadline") else ""
    return (f"📋 Задание #{t['id']}\n\n{t['text']}{dl}\n"
            f"Для: {dict(POS_FILTERS).get(t['pos'], 'всех')}\n"
            f"Статус: {status_map.get(t['status'], t['status'])}{u_done}")


def task_list_kb(tasks, uid):
    rows = [[f"#{t['id']} {(t['text'] or '')[:40]}", f"task:view:{t['id']}"] for t in tasks]
    rows.append(["⬅️ Назад", "back:menu"])
    return kb(rows)


def visible_tasks(u):
    tasks = db.query(
        "SELECT * FROM tasks WHERE status='active' AND deleted_at IS NULL AND "
        "(pos IS NULL OR pos=? OR pos='all') ORDER BY id DESC", (u["pos"] or "",))
    return tasks


@router.message(F.text == "📋 Задания")
async def my_tasks(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    tasks = visible_tasks(u)
    if not tasks:
        await m.answer("📭 Активных заданий для вас нет.",
                       reply_markup=keyboards.main_menu(u))
        return
    await m.answer("📋 Задания для вашей должности:", reply_markup=task_list_kb(tasks, u))


@router.callback_query(F.data.startswith("task:view:"))
async def task_view(c: CallbackQuery, state: FSMContext):
    tid = int(c.data.split(":")[2])
    t = db.get("SELECT * FROM tasks WHERE id=?", (tid,))
    if not t:
        await c.answer("Задание не найдено", show_alert=True)
        return
    u = db.get_user(c.from_user.id)
    rows = []
    if t["status"] == "active" and not u["banned"]:
        w = db.get("SELECT id,status FROM works WHERE task_id=? AND user_id=? AND "
                   "kind IN ('free','form') ORDER BY id DESC", (tid, u["id"]))
        if not w or w["status"] in ("reviewed", "rejected"):
            rows.append(["📤 Сдать работу", f"task:submit:{tid}"])
    services_txt = ""
    closers = db.jload(t["closers"], [])
    can_close = ((closers == ["all"]) or
                 ("admins" in closers and u["role"] >= 1) or
                 ("owner" in closers and u["role"] >= 4) or u["role"] >= 3)
    if can_close and t["status"] == "active":
        rows.append(["✅ Закрыть задание", f"task:close:{tid}"])
    if u["role"] >= 1:
        rows.append(["⭐ Работы по заданию", f"task:works:{tid}"])
    if u["role"] >= 3 or (t["created_by"] == u["id"]):
        rows.append(["🗑 Удалить", f"task:del:{tid}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await send_content(c.bot, c.from_user.id, task_text(t, u), t["aid"], kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("task:submit:"))
async def task_submit(c: CallbackQuery, state: FSMContext):
    tid = int(c.data.split(":")[2])
    t = db.get("SELECT * FROM tasks WHERE id=?", (tid,))
    forms = db.query("SELECT * FROM forms")
    rows = [
        ["📝 Свободный отчёт", f"wkind:free:{tid}:0"],
        ["📄 По форме", f"form_pick:{tid}"],
        ["✏️ Корректировка", f"correction_pick:{tid}"],
        ["💬 Ответ на другое задание", f"wkind:reply:{tid}:0"],
    ]
    if not forms:
        rows.pop(1)
    rows.append(["❌ Отмена", f"task:view:{tid}"])
    await c.message.answer("📤 Как сдаём работу?", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("form_pick:"))
async def form_pick(c: CallbackQuery, state: FSMContext):
    tid = int(c.data.split(":")[1])
    forms = db.query("SELECT * FROM forms")
    rows = [[f["title"], f"wkind:form:{tid}:{f['id']}"] for f in forms]
    rows.append(["❌ Отмена", f"task:view:{tid}"])
    await c.message.edit_reply_markup(reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("correction_pick:"))
async def correction_pick(c: CallbackQuery, state: FSMContext):
    tid = int(c.data.split(":")[1])
    u = db.get_user(c.from_user.id)
    works = db.query(
        "SELECT * FROM works WHERE user_id=? AND task_id=? AND status='needs_correction' "
        "ORDER BY id DESC", (u["id"], tid))
    if not works:
        await c.answer("Нет работ, требующих корректировки по этому заданию",
                       show_alert=True)
        return
    rows = [[f"Работа #{w['id']} ({(w['text'] or '')[:30]})",
             f"wkind:correction:{tid}:{w['id']}"] for w in works]
    rows.append(["❌ Отмена", f"task:view:{tid}"])
    await c.message.edit_reply_markup(reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("wkind:"))
async def work_kind(c: CallbackQuery, state: FSMContext):
    _, kind, tid, parent = c.data.split(":")
    await state.set_state(WorkSubmit.content)
    await state.update_data(kind=kind, task_id=int(tid), parent_id=int(parent),
                            files=[], text="")
    hints = {
        "free": "Отправьте текст, фото, файлы (можно несколькими сообщениями).",
        "form": "Заполните форму: ответьте на каждый вопрос одним сообщением.",
        "correction": "Отправьте исправленную работу (текст, фото, файлы).",
        "reply": "Отправьте ответ на задание (текст, фото, файлы).",
    }
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    rk = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Отправить"),
                                        KeyboardButton(text="❌ Отмена")]],
                             resize_keyboard=True)
    if kind == "form":
        form = db.get("SELECT * FROM forms WHERE id=?", (int(parent),))
        fields = db.jload(form["fields"]) if form else []
        await state.update_data(form_fields=fields, form_idx=0, answers=[])
        await c.message.answer(f"Форма «{form['title']}».\n"
                               f"Вопрос 1 из {len(fields)}:\n{fields[0] if fields else ''}",
                               reply_markup=rk)
    else:
        await c.message.answer(hints[kind], reply_markup=rk)
    await c.answer()


@router.message(WorkSubmit.content, F.text == "❌ Отмена")
async def work_cancel(m: Message, state: FSMContext):
    await state.clear()
    u = db.get_user(m.from_user.id)
    await m.answer("❌ Отменено", reply_markup=keyboards.main_menu(u))


@router.message(WorkSubmit.content)
async def work_content(m: Message, state: FSMContext):
    data = await state.get_data()
    if m.text == "✅ Отправить":
        files = data.get("files", [])
        text = data.get("text", "")
        kind = data["kind"]
        tid = data["task_id"]
        uid = m.from_user.id
        u = db.get_user(uid)
        if kind == "form" and data.get("form_fields") and \
                data.get("form_idx", 0) < len(data["form_fields"]):
            answers = data.get("answers", [])
            answers.append(text)
            await state.update_data(answers=answers, form_idx=len(answers), text="")
            await m.answer(f"Вопрос {len(answers)+1} из {len(data['form_fields'])}:\n"
                           f"{data['form_fields'][len(answers)]}")
            return
        if not text and not files:
            await m.answer("⚠️ Пустая работа — добавьте текст или файл.")
            return
        wid = db.execute(
            "INSERT INTO works(task_id,user_id,kind,parent_id,text,files,form_id,"
            "answers,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (tid if kind != "reply" else tid, uid, kind,
             data.get("parent_id") or None, text,
             __import__("json").dumps(files, ensure_ascii=False),
             data.get("parent_id") if kind == "form" else None,
             __import__("json").dumps(data.get("answers", []), ensure_ascii=False),
             "submitted", db.now()))
        task = db.get("SELECT * FROM tasks WHERE id=?", (tid,))
        w = db.get("SELECT * FROM works WHERE id=?", (wid,))
        kind_names = {"free": "Свободный отчёт", "form": "По форме",
                      "correction": "Корректировка", "reply": "Ответ на задание"}
        notif = (f"📤 Новая работа #{wid} ({kind_names[kind]})\n"
                 f"От: {u['name']} (id {uid})\n"
                 f"Задание: #{tid} {(task['text'] or '')[:60] if task else ''}\n\n{text}")
        for rid_ in services.curators_for_pos(u["pos"]):
            await send_content(services.get_bot(), rid_, notif, None, files,
                               kb([["⭐ Оценить", f"wr:grade:{wid}"],
                                   ["👁 Открыть", f"wr:view:{wid}"]]))
        await state.clear()
        await m.answer("✅ Работа отправлена куратору и владельцу!",
                       reply_markup=keyboards.main_menu(u))
        services.log(uid, "work_submit", f"work {wid} task {tid}")
        return

    files = data.get("files", [])
    new_files = file_list_from_message(m)
    if new_files:
        files.extend(new_files)
    text = (data.get("text", "") + ("\n" if data.get("text") and m.text else "") +
            (m.text or m.caption or ""))
    if data.get("kind") == "form":
        text = m.text or m.caption or ""
    await state.update_data(files=files, text=text)
    await m.answer("✅ Принято. Можно дополнить или нажать «✅ Отправить».")


@router.message(F.text == "📤 Мои работы")
async def my_works(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    works = db.query("SELECT * FROM works WHERE user_id=? ORDER BY id DESC LIMIT 20",
                     (u["id"],))
    if not works:
        await m.answer("📭 У вас пока нет работ.", reply_markup=keyboards.main_menu(u))
        return
    status_map = {"submitted": "⏳ На проверке", "reviewed": "✅ Проверена",
                  "needs_correction": "✏️ Нужна корректировка", "rejected": "❌ Отклонена"}
    lines = ["📤 Мои работы:\n"]
    rows = []
    for w in works:
        lines.append(f"#{w['id']} — задание #{w['task_id']} — {status_map.get(w['status'], w['status'])}"
                     + (f" — {w['points']:.1f} б." if w["points"] else ""))
        if w["status"] == "needs_correction":
            rows.append([f"✏️ Исправить #{w['id']}", f"fix:{w['task_id']}:{w['id']}"])
        elif w["status"] == "reviewed":
            rows.append([f"👁 Отзыв #{w['id']}", f"wr:feedback:{w['id']}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await m.answer("\n".join(lines), reply_markup=kb(rows))


@router.callback_query(F.data.startswith("fix:"))
async def fix_work(c: CallbackQuery, state: FSMContext):
    _, tid, parent = c.data.split(":")
    await state.set_state(WorkSubmit.content)
    await state.update_data(kind="correction", task_id=int(tid), parent_id=int(parent),
                            files=[], text="")
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    rk = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Отправить"),
                                        KeyboardButton(text="❌ Отмена")]],
                             resize_keyboard=True)
    await c.message.answer("✏️ Отправьте исправленную работу:", reply_markup=rk)
    await c.answer()


@router.callback_query(F.data.startswith("wr:feedback:"))
async def work_feedback(c: CallbackQuery):
    wid = int(c.data.split(":")[2])
    w = db.get("SELECT * FROM works WHERE id=?", (wid,))
    if not w or w["user_id"] != c.from_user.id:
        await c.answer("Нет доступа", show_alert=True)
        return
    text = (f"👁 Отзыв по работе #{wid}\n\n"
            f"Оценка: {w['grade'] or '—'}/10\n"
            f"Итог: {w['result'] or '—'}\n"
            f"Баллы: {w['points']:.1f}\n"
            f"Комментарий: {w['comment'] or '—'}")
    await send_content(c.bot, c.from_user.id, text, w["comment_photo"])
    await c.answer()


async def _finish_grade(bot, w):
    task = db.get("SELECT * FROM tasks WHERE id=?", (w["task_id"],))
    u = db.get_user(w["user_id"])
    base = config.RESULT_POINTS.get(w["result"], 0)
    pts = base + (w["grade"] or 0) * 0.5
    db.execute("UPDATE works SET points=?, reviewed_at=?, status='reviewed' WHERE id=?",
               (pts, db.now(), w["id"]))
    await services.add_points(w["user_id"], pts, f"задание #{w['task_id']}")
    text = (f"{support_phrase()}\n\n⭐ Ваша работа #{w['id']} проверена!\n"
            f"Задание: #{w['task_id']}\n"
            f"Оценка: {w['grade']}/10\nИтог: {w['result']}\n"
            f"Начислено баллов: +{pts:.1f}\n"
            f"Комментарий: {w['comment'] or '—'}")
    if w["result"] in ("🔴 Неправильно", "❌ Совсем неверно"):
        text += ("\n\n✏️ Работа требует корректировки — исправьте и отправьте снова "
                 "через «📤 Мои работы».")
        db.execute("UPDATE works SET status='needs_correction' WHERE id=?", (w["id"],))
    await send_content(bot, w["user_id"], text, w["comment_photo"])
    db.log_system("grade", f"work {w['id']} by {w['reviewer_id']}: {pts}")


@router.callback_query(F.data.startswith("wr:view:"))
async def work_view(c: CallbackQuery):
    wid = int(c.data.split(":")[2])
    w = db.get("SELECT * FROM works WHERE id=?", (wid,))
    if not w:
        await c.answer("Не найдено", show_alert=True)
        return
    u = db.get_user(c.from_user.id)
    if u["role"] < 1 and w["user_id"] != u["id"]:
        await c.answer("Нет доступа", show_alert=True)
        return
    owner = db.get_user(w["user_id"])
    text = (f"📤 Работа #{wid}\nОт: {owner['name']} (id {owner['id']})\n"
            f"Тип: {w['kind']}\nЗадание: #{w['task_id']}\n\n{w['text'] or ''}")
    w = db.get("SELECT * FROM works WHERE id=?", (wid,))
    rows = []
    if w["status"] == "submitted" and u["role"] >= 1:
        rows.append(["⭐ Оценить", f"wr:grade:{wid}"])
    if w["status"] == "reviewed" and u["role"] >= 1:
        rows.append(["🥇 Лучшая работа", f"wr:best:{wid}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await send_content(c.bot, c.from_user.id, text, None, extract_files(w), kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("task:works:"))
async def task_works(c: CallbackQuery):
    tid = int(c.data.split(":")[2])
    works = db.query("SELECT * FROM works WHERE task_id=? ORDER BY id DESC", (tid,))
    if not works:
        await c.answer("Работ пока нет", show_alert=True)
        return
    rows = []
    for w in works:
        owner = db.get_user(w["user_id"])
        st = {"submitted": "⏳", "reviewed": "✅", "needs_correction": "✏️"}.get(w["status"], "")
        rows.append([f"#{w['id']} {owner['name'] if owner else '?'} {st}",
                     f"wr:view:{w['id']}"])
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer(f"⭐ Работы по заданию #{tid}:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("wr:grade:"))
async def grade_start(c: CallbackQuery, state: FSMContext):
    wid = int(c.data.split(":")[2])
    w = db.get("SELECT * FROM works WHERE id=?", (wid,))
    if not w or w["status"] != "submitted":
        await c.answer("Работа уже проверена", show_alert=True)
        return
    await state.set_state(Grade.grade)
    await state.update_data(wid=wid)
    await c.message.answer("Оцените работу от 1 до 10 (числом):")
    await c.answer()


@router.message(Grade.grade, F.text)
async def grade_num(m: Message, state: FSMContext):
    if not m.text.strip().isdigit() or not (1 <= int(m.text.strip()) <= 10):
        await m.answer("Введите число от 1 до 10:")
        return
    await state.update_data(grade=int(m.text.strip()))
    await state.set_state(Grade.result)
    rows = [[r] for r in config.RESULT_POINTS]
    await m.answer("Итог работы:", reply_markup=kb(rows + [["⬅️ Отмена", "back:menu"]]))


@router.message(Grade.result, F.text.in_(list(config.RESULT_POINTS.keys())))
async def grade_result(m: Message, state: FSMContext):
    await state.update_data(result=m.text)
    await state.set_state(Grade.comment)
    await m.answer("💬 Комментарий (или «нет»):")


@router.message(Grade.comment, F.text)
async def grade_comment(m: Message, state: FSMContext):
    await state.update_data(comment=None if m.text.lower() == "нет" else m.text)
    await state.set_state(Grade.photo)
    await m.answer("📷 Прикрепите фото к комментарию (или «нет»):")


@router.message(Grade.photo, F.photo)
async def grade_photo(m: Message, state: FSMContext):
    await state.update_data(photo=m.photo[-1].file_id)
    await do_grade(m, state)


@router.message(Grade.photo, F.text == "нет")
async def grade_nophoto(m: Message, state: FSMContext):
    await do_grade(m, state)


async def do_grade(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    uid = data["wid"]
    reviewer = db.get_user(m.from_user.id)
    grade = data.get("grade")
    result = data.get("result") or "🟢 Правильно"
    comment = data.get("comment")
    photo = data.get("photo")
    db.execute(
        "UPDATE works SET grade=?, result=?, comment=?, comment_photo=?, reviewer_id=? "
        "WHERE id=?", (grade, result, comment, photo, m.from_user.id, uid))
    w = db.get("SELECT * FROM works WHERE id=?", (uid,))
    await _finish_grade(m.bot, w)
    await m.answer("✅ Оценка сохранена, участник уведомлён.",
                   reply_markup=keyboards.main_menu(reviewer))


@router.callback_query(F.data.startswith("wr:best:"))
async def mark_best(c: CallbackQuery):
    wid = int(c.data.split(":")[2])
    w = db.get("SELECT * FROM works WHERE id=?", (wid,))
    if not w:
        await c.answer("Не найдено", show_alert=True)
        return
    db.execute("UPDATE works SET best=0 WHERE task_id=?", (w["task_id"],))
    db.execute("UPDATE works SET best=1 WHERE id=?", (wid,))
    await services.add_points(w["user_id"], 3, "лучшая работа")
    await services.notify(w["user_id"], "🥇 Ваша работа признана лучшей! +3 балла")
    await c.answer("Отмечено как лучшая работа (+3 балла автору)")


@router.callback_query(F.data.startswith("task:close:"))
async def task_close(c: CallbackQuery):
    tid = int(c.data.split(":")[2])
    t = db.get("SELECT * FROM tasks WHERE id=?", (tid,))
    if not t or t["status"] != "active":
        await c.answer("Недоступно", show_alert=True)
        return
    db.execute("UPDATE tasks SET status='closed', done_at=?, closed_by=? WHERE id=?",
               (db.now(), c.from_user.id, tid))
    db.to_archive("tasks", tid)
    services.log(c.from_user.id, "task_close", str(tid))
    await services.publish(c.bot, "task", f"✅ Задание #{tid} закрыто.")
    await c.message.answer(f"✅ Задание #{tid} закрыто.")
    await c.answer()


@router.message(F.text == "🗑 Удалить задание")
async def noop(m: Message):
    pass


async def delete_task(t):
    db.take_to_trash("tasks", t["id"])
    db.execute("UPDATE tasks SET status='deleted', deleted_at=? WHERE id=?",
               (db.now(), t["id"]))


@router.callback_query(F.data.startswith("task:del:"))
async def task_del(c: CallbackQuery):
    tid = int(c.data.split(":")[2])
    t = db.get("SELECT * FROM tasks WHERE id=?", (tid,))
    if not t:
        await c.answer("Не найдено", show_alert=True)
        return
    await delete_task(t)
    services.log(c.from_user.id, "task_delete", str(tid))
    await c.message.answer(f"🗑 Задание #{tid} перемещено в корзину (48 ч на возврат).")
    await c.answer()


@router.callback_query(F.data.startswith("tpl_use:"))
async def tpl_use(c: CallbackQuery, state: FSMContext):
    tpl_id = int(c.data.split(":")[1])
    t = db.get("SELECT * FROM templates WHERE id=?", (tpl_id,))
    if not t:
        await c.answer("Шаблон не найден", show_alert=True)
        return
    await state.set_state(TaskCreate.pos)
    await state.update_data(text=t["text"], photo=t["photo"], template_id=tpl_id)
    rows = [[name, f"tpos:{key}"] for key, name in POS_FILTERS]
    await c.message.answer(f"📑 Шаблон «{t['title']}» загружен.\nДля кого задание?",
                           reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("tpos:"))
async def tpl_pos(c: CallbackQuery, state: FSMContext):
    pos = c.data.split(":")[1]
    await state.update_data(pos=pos)
    await ask_closers(c.message, state)


async def ask_closers(message, state: FSMContext):
    await state.set_state(TaskCreate.closers)
    rows = [["👥 Все участники", "tclosers:all"], ["🛠 Админы", "tclosers:admins"],
            ["👑 Только владелец", "tclosers:owner"]]
    await message.answer("❇️ Кто может закрыть задание?", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("tclosers:"))
async def tpl_closers(c: CallbackQuery, state: FSMContext):
    closers = c.data.split(":")[1]
    await state.update_data(closers=[closers])
    await state.set_state(TaskCreate.deadline)
    await c.message.answer("⏰ Срок выполнения (ДД.ММ.ГГГГ ЧЧ:ММ) или «нет»:")


@router.message(TaskCreate.deadline, F.text)
async def task_deadline(m: Message, state: FSMContext):
    data = await state.get_data()
    deadline = None
    if m.text.lower() != "нет":
        from utils import parse_dt
        dt = parse_dt(m.text)
        if not dt:
            await m.answer("Не понял дату. Пример: 25.12.2025 18:00 или «нет»:")
            return
        deadline = dt.strftime("%Y-%m-%d %H:%M:%S")
    u = db.get_user(m.from_user.id)
    tid = db.execute(
        "INSERT INTO tasks(text,aid,pos,src,status,closers,deadline,created_at,"
        "created_by,template_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (data["text"], data.get("photo"), data.get("pos"),
         data.get("src", "manual"), "active", __import__("json").dumps(data["closers"]),
         deadline, db.now(), u["id"], data.get("template_id")))
    await state.clear()
    t = db.get("SELECT * FROM tasks WHERE id=?", (tid,))
    n = await services.publish(m.bot, "task", task_text(t), t["aid"],
                               kb([["👁 Открыть", f"task:view:{tid}"]]))
    services.log(u["id"], "task_create", str(tid))
    await m.answer(f"✅ Задание #{tid} создано и опубликовано в {n} чатах.",
                   reply_markup=keyboards.main_menu(u))


@router.callback_query(F.data.startswith("t:new"))
async def task_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not u or u["role"] < 1 or not db.has_right(u, "tasks"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(TaskCreate.content)
    tpls = db.query("SELECT * FROM templates ORDER BY id DESC LIMIT 10")
    rows = [[f"📑 {t['title'][:30]}", f"tpl_use:{t['id']}"] for t in tpls]
    rows.append(["✍️ Написать с нуля", "t:new_manual"])
    await c.message.answer("📋 Создание задания. Из шаблона или вручную?",
                           reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("t:new_manual"))
async def task_new_manual(c: CallbackQuery, state: FSMContext):
    await state.set_state(TaskCreate.content)
    await c.message.answer("📋 Пришлите текст задания (или фото с подписью):",
                           reply_markup=keyboards.rkb([["❌ Отмена"]]))
    await c.answer()


@router.message(TaskCreate.content, F.photo)
async def task_content_photo(m: Message, state: FSMContext):
    await state.update_data(text=m.caption or "", photo=m.photo[-1].file_id)
    await ask_pos(m, state)


@router.message(TaskCreate.content, F.text == "❌ Отмена")
async def task_content_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❌ Отменено", reply_markup=keyboards.main_menu(db.get_user(
        m.from_user.id)))


@router.message(TaskCreate.content, F.text)
async def task_content(m: Message, state: FSMContext):
    await state.update_data(text=m.text, photo=None, src="manual")
    await ask_pos(m, state)


@router.message(TaskCreate.content)
async def task_content_other(m: Message, state: FSMContext):
    await m.answer("Пришлите текст или фото с подписью.")


async def ask_pos(m: Message, state: FSMContext):
    await state.set_state(TaskCreate.pos)
    rows = [[name, f"tpos:{key}"] for key, name in POS_FILTERS]
    await m.answer("👔 Для кого задание?", reply_markup=kb(rows))


async def task_admin_menu(u):
    rows = []
    if db.has_right(u, "tasks"):
        rows.append(["➕ Создать задание", "t:new"])
        rows.append(["⏳ Работы на проверке", "ad:queue"])
        if db.has_right(u, "templates"):
            rows.append(["📑 Шаблоны", "ad:templates"])
        rows.append(["📄 Формы", "ad:forms"])
    if db.has_right(u, "checklists"):
        rows.append(["✅ Чек-листы", "cl:backtomenu"])
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
