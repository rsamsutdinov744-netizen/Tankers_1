import json
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import config
import database as db
import services
from states import MaterialCreate, Announcement
from utils import kb, send_content, fmt_name

router = Router()

KIND_ROWS = [["📝 Текст", "mk:text"], ["🖼 Фото", "mk:photo"], ["🔗 Ссылка", "mk:url"],
             ["📎 Файл", "mk:file"], ["🎬 Видео", "mk:video"]]


def visible_materials(u, tab_only=False):
    rows = db.query("SELECT * FROM materials ORDER BY pinned DESC, id DESC LIMIT 50")
    out = []
    for mt in rows:
        vis = db.jload(mt["visible"], {"mode": "all"})
        mode = vis.get("mode", "all")
        if tab_only and mode == "all":
            pass
        if mode == "all":
            out.append(mt)
        elif mode == "list" and u["id"] in vis.get("users", []):
            out.append(mt)
        elif mode == "tab" and not tab_only:
            out.append(mt)
    return out


@router.message(F.text == "📚 Материалы")
async def materials_menu(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    mats = [mt for mt in visible_materials(u, tab_only=True)]
    rows = [[f"{'📌 ' if mt['pinned'] else ''}{mt['title'][:40]}", f"mat:{mt['id']}"]
            for mt in mats]
    if db.has_right(u, "materials"):
        rows.append(["➕ Добавить материал", "mat:new"])
        rows.append(["📋 Управление", "mat:manage"])
    rows.append(["⬅️ Назад", "back:menu"])
    await m.answer("📚 Материалы:", reply_markup=kb(rows))


async def material_content(mt, for_uid=None):
    return None


@router.callback_query(F.data.startswith("mat:"))
async def mat_view(c: CallbackQuery):
    mid = int(c.data.split(":")[1])
    mt = db.get("SELECT * FROM materials WHERE id=?", (mid,))
    if not mt:
        await c.answer("Не найдено", show_alert=True)
        return
    text = f"📚 {mt['title']}\n\n{mt['text'] or ''}"
    if mt["url"]:
        text += f"\n\n🔗 {mt['url']}"
    files = []
    if mt["file_id"]:
        t = {"photo": "photo", "video": "video", "file": "document"}.get(mt["kind"],
                                                                         "document")
        files = [{"type": t, "id": mt["file_id"]}]
    rows = []
    if mt["url"]:
        from aiogram.types import InlineKeyboardButton
        rows.insert(0, [InlineKeyboardButton(text="🔗 Открыть ссылку", url=mt["url"])])
    u = db.get_user(c.from_user.id)
    if db.has_right(u, "materials"):
        from aiogram.types import InlineKeyboardButton
        rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"matdel:{mid}"),
                     InlineKeyboardButton(text="📌 Закрепить",
                                          callback_data=f"matpin:{mid}")])
    await send_content(c.bot, c.from_user.id, text, None, files,
                       None if not rows else __import__("aiogram").types.\
                           InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()


@router.callback_query(F.data.startswith("matpin:"))
async def mat_pin(c: CallbackQuery):
    mid = int(c.data.split(":")[1])
    mt = db.get("SELECT * FROM materials WHERE id=?", (mid,))
    db.execute("UPDATE materials SET pinned=? WHERE id=?", (0 if mt["pinned"] else 1, mid))
    await c.answer("Закрепление изменено")


@router.callback_query(F.data.startswith("matdel:"))
async def mat_del(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "materials"):
        await c.answer("Нет прав", show_alert=True)
        return
    mid = int(c.data.split(":")[1])
    db.take_to_trash("materials", mid)
    db.execute("DELETE FROM materials WHERE id=?", (mid,))
    services.log(c.from_user.id, "material_del", str(mid))
    await c.answer("Удалено (в корзине 48 ч)")


@router.callback_query(F.data.startswith("mat:manage"))
async def mat_manage(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "materials"):
        await c.answer("Нет прав", show_alert=True)
        return
    mats = db.query("SELECT * FROM materials ORDER BY id DESC LIMIT 20")
    if not mats:
        await c.answer("Материалов нет", show_alert=True)
        return
    vis = {"all": "👥", "tab": "📚", "list": "👤"}
    rows = [[f"{vis.get((db.jload(mt['visible'], {'mode': 'all'}).get('mode','all')),'👥')} "
             f"{mt['title'][:35]}", f"mat:{mt['id']}"] for mt in mats]
    rows.append(["⬅️ Назад", "back:menu"])
    await c.message.answer("📋 Управление материалами:", reply_markup=kb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("mat:new"))
async def mat_new(c: CallbackQuery, state: FSMContext):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "materials"):
        await c.answer("Нет прав", show_alert=True)
        return
    await state.set_state(MaterialCreate.kind)
    await c.message.answer("📚 Тип материала:", reply_markup=kb(KIND_ROWS + [["⬅️ Отмена",
                                                                              "back:menu"]]))
    await c.answer()


@router.callback_query(F.data.startswith("mk:"))
async def mk_kind(c: CallbackQuery, state: FSMContext):
    kind = c.data.split(":")[1]
    await state.update_data(kind=kind)
    await state.set_state(MaterialCreate.title)
    await c.message.answer("📝 Название материала:")
    await c.answer()


@router.message(MaterialCreate.title, F.text)
async def mat_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    data = await state.get_data()
    kind = data["kind"]
    await state.set_state(MaterialCreate.content)
    if kind == "text":
        await m.answer("📝 Текст материала:")
    elif kind == "photo":
        await m.answer("🖼 Пришлите фото (подпись = описание материала):")
    elif kind == "url":
        await state.set_state(MaterialCreate.url)
        await m.answer("🔗 Пришлите ссылку:")
    elif kind == "file":
        await m.answer("📎 Пришлите файл (подпись = описание):")
    else:
        await m.answer("🎬 Пришлите видео (подпись = описание):")


@router.message(MaterialCreate.content, F.photo)
async def mat_content_photo(m: Message, state: FSMContext):
    await state.update_data(file_id=m.photo[-1].file_id, text=m.caption or "")
    await mat_visible(m, state)


@router.message(MaterialCreate.content, F.document)
async def mat_content_doc(m: Message, state: FSMContext):
    await state.update_data(file_id=m.document.file_id, text=m.caption or "")
    await mat_visible(m, state)


@router.message(MaterialCreate.content, F.video)
async def mat_content_video(m: Message, state: FSMContext):
    await state.update_data(file_id=m.video.file_id, text=m.caption or "")
    await mat_visible(m, state)


@router.message(MaterialCreate.content, F.text)
async def mat_content_text(m: Message, state: FSMContext):
    await state.update_data(file_id=None, text=m.text)
    await mat_visible(m, state)


@router.message(MaterialCreate.url, F.text)
async def mat_url(m: Message, state: FSMContext):
    if not m.text.startswith(("http://", "https://", "tg://")):
        await m.answer("Это не похоже на ссылку. Пример: https://example.com")
        return
    await state.update_data(url=m.text)
    await mat_visible(m, state)


async def mat_visible(m: Message, state: FSMContext):
    await state.set_state(MaterialCreate.visible)
    rows = [["👥 Всем в главное меню", "mv:all"], ["📚 Только во вкладке", "mv:tab"],
            ["👤 Конкретным участникам", "mv:list"]]
    await m.answer("👁 Кому виден материал?", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("mv:"))
async def mv_choice(c: CallbackQuery, state: FSMContext):
    mode = c.data.split(":")[1]
    data = await state.get_data()
    if mode == "list":
        members = db.query(
            "SELECT * FROM users WHERE banned=0 AND leave_at IS NULL LIMIT 15")
        rows = [[f"{mm['name']} (id {mm['id']})", f"mvu:{mm['id']}"] for mm in members]
        rows.append(["✅ Готово", "mvu:done"])
        await state.update_data(vis_users=[], vis_mode="list")
        await state.set_state(MaterialCreate.users)
        await c.message.answer("👤 Выберите участников:", reply_markup=kb(rows))
        await c.answer()
        return
    await state.update_data(vis_mode=mode)
    await _save_material(c, state)
    await c.answer()


@router.callback_query(F.data.startswith("mvu:"))
async def mvu_pick(c: CallbackQuery, state: FSMContext):
    val = c.data.split(":")[1]
    data = await state.get_data()
    if val == "done":
        users = data.get("vis_users", [])
        if not users:
            await c.answer("Никого не выбрано", show_alert=True)
            return
        await _save_material(c, state)
        await c.answer()
        return
    users = data.get("vis_users", [])
    if int(val) not in users:
        users.append(int(val))
        await state.update_data(vis_users=users)
        await c.answer(f"✅ Добавлен ({len(users)})")


async def _save_material(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    u = db.get_user(c.from_user.id)
    vis = {"mode": data.get("vis_mode", "all")}
    if vis["mode"] == "list":
        vis["users"] = data.get("vis_users", [])
    mid = db.execute(
        "INSERT INTO materials(kind,title,text,file_id,url,pinned,visible,created_by,"
        "created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (data["kind"], data["title"], data.get("text"), data.get("file_id"),
         data.get("url"), 0, json.dumps(vis, ensure_ascii=False), u["id"], db.now()))
    await state.clear()
    services.log(u["id"], "material_new", str(mid))
    if vis["mode"] == "all":
        text = f"📚 Новый материал: {data['title']}\n\n{data.get('text') or ''}"
        files = []
        if data.get("file_id"):
            t = {"photo": "photo", "video": "video", "file": "document"}.get(data["kind"],
                                                                             "document")
            files = [{"type": t, "id": data["file_id"]}]
        await services.publish(c.bot, "material", text, None, files,
                               kb([["👁 Открыть", f"mat:{mid}"]]))
    await c.message.answer("✅ Материал сохранён!",
                           reply_markup=keyboards.main_menu(u))


@router.message(F.text == "📢 Объявления")
async def announcements(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    if db.has_right(u, "announcements"):
        await state.set_state(Announcement.content)
        await m.answer("📢 Пришлите текст объявления (можно фото с подписью).\n"
                       "Оно уйдёт в чаты объявлений и всем участникам.",
                       reply_markup=keyboards.rkb([["❌ Отмена"]]))
    else:
        mats = db.query("SELECT * FROM materials WHERE 1=0")
        await m.answer("📚 Другие материалы", reply_markup=keyboards.main_menu(u))


@router.message(Announcement.content, F.photo)
async def ann_photo(m: Message, state: FSMContext):
    n = await services.publish(m.bot, "announcement", m.caption or "",
                               m.photo[-1].file_id)
    await services.notify_admins_with_right("announcements",
                                            f"📢 (копия админам)", warn=False)
    await state.clear()
    u = db.get_user(m.from_user.id)
    await m.answer(f"✅ Объявление отправлено в {n} чатов.",
                   reply_markup=keyboards.main_menu(u))
    services.log(m.from_user.id, "announcement", str(n))


@router.message(Announcement.content, F.text)
async def ann_text(m: Message, state: FSMContext):
    if m.text == "❌ Отмена":
        await state.clear()
        await m.answer("❌ Отменено", reply_markup=keyboards.main_menu(
            db.get_user(m.from_user.id)))
        return
    members = db.query("SELECT id FROM users WHERE banned=0 AND leave_at IS NULL")
    n = await services.publish(m.bot, "announcement", m.text)
    sent = 0
    for mem in members:
        if await send_content(m.bot, mem["id"], m.text, warn=False):
            sent += 1
    await state.clear()
    u = db.get_user(m.from_user.id)
    await m.answer(f"✅ Объявление отправлено в {n} чатов и {sent} участникам.",
                   reply_markup=keyboards.main_menu(u))
    services.log(m.from_user.id, "announcement", f"{n} chats, {sent} users")
