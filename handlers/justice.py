from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import config
import database as db
import services
from states import *
from utils import kb, user_line, fmt_name

router = Router()


@router.callback_query(F.data.startswith("appeal_start:"))
async def appeal_start(c: CallbackQuery, state: FSMContext):
    parts = c.data.split(":")
    vtype_full = parts[1]
    uid = int(parts[2])
    if c.from_user.id != uid:
        await c.answer("Нет доступа", show_alert=True)
        return
    u = db.get_user(uid)
    await state.set_state(AppealStart.confirm)
    await state.update_data(appeal_vtype=vtype_full, uid=uid)
    await c.message.answer(
        "📣 Подать апелляцию? Проголосуют все участники "
        "(новичок — 1 голос, остальные — 2). При ≥50% «за» — повышение.\n\n"
        "Вы увидите всю свою историю: наказания, повышения, баллы, отказы.",
        reply_markup=kb([[["✅ Подать", f"appeal_go:yes"],
                          ["❌ Отмена", f"appeal_go:no"]]]))
    await c.answer()


@router.callback_query(F.data.startswith("appeal_go:"))
async def appeal_go(c: CallbackQuery, state: FSMContext):
    choice = c.data.split(":")[1]
    data = await state.get_data()
    await state.clear()
    if choice != "yes":
        await c.answer("Отменено")
        return
    uid = data["uid"]
    vtype = data["appeal_vtype"]
    u = db.get_user(uid)
    already = db.get("SELECT id FROM votes WHERE type=? AND target_id=? AND status='active'",
                     (vtype, uid))
    if already:
        await c.answer("Апелляция уже идёт", show_alert=True)
        return
    # история для участника
    puns = db.query("SELECT * FROM punishments WHERE user_id=?", (uid,))
    votes_hist = db.query("SELECT * FROM votes WHERE target_id=? ORDER BY id DESC LIMIT 5",
                          (uid,))
    hist_lines = [f"Статус: {config.STATUS_NAMES[u['status']]}, "
                  f"должность: {config.POSITIONS.get(u['pos'], '—')}, "
                  f"баллы: {u['points']:.1f}",
                  f"Наказаний всего: {len(puns)}"]
    reasons = []
    for v in votes_hist:
        if v["reason"]:
            reasons.append(v["reason"])
    if reasons:
        hist_lines.append("Причины прошлых отказов: " + "; ".join(reasons))
    full_hist = "\n".join(hist_lines)
    vid = services.create_vote(vtype, uid)
    if not vid:
        await c.message.answer("Не удалось создать апелляцию.")
        return
    voters = db.query("SELECT * FROM users WHERE banned=0 AND leave_at IS NULL")
    vtxt = (f"📣 АПЕЛЛЯЦИЯ ({'первая' if vtype.endswith('1') else 'вторая, финальная'})\n\n"
            f"Участник: {user_line(u)}\n{full_hist}\n\n"
            f"Голосуйте: повышение до "
            f"{'«Лучший участник»' if vtype.startswith('best') else '«Ведущий»'}?")
    count = 0
    for v in voters:
        if v["id"] == uid:
            await services.notify(v["id"], f"📣 Ваша апелляция открыта:\n\n{full_hist}")
            continue
        await services.notify(v["id"], vtxt,
                              kbd=kb([[["✅ Повысить", f"appealvote:{vid}:yes"],
                                       ["❌ Против", f"appealvote:{vid}:no"]]]),
                              warn=False)
        count += 1
    from datetime import datetime, timedelta
    db.execute("UPDATE votes SET deadline=? WHERE id=?",
               ((datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), vid))
    await c.message.answer(f"✅ Апелляция открыта, уведомлено {count} участников.")
    services.log(uid, "appeal", vtype)
    await c.answer()


@router.callback_query(F.data.startswith("appealvote:"))
async def appeal_vote(c: CallbackQuery):
    _, vid_s, choice = c.data.split(":")
    vid = int(vid_s)
    vote = db.get("SELECT * FROM votes WHERE id=?", (vid,))
    if not vote or vote["status"] != "active":
        await c.answer("Голосование завершено", show_alert=True)
        return
    u = db.get_user(c.from_user.id)
    if not u or u["id"] == vote["target_id"]:
        await c.answer("Нельзя голосовать", show_alert=True)
        return
    # не даём голосовать до дедлайна всем сразу? голосуем сразу
    await services.vote_cast(vid, c.from_user.id, choice)
    await c.answer("Голос учтён")


async def appeal_deadline_tick():
    if not services.get_bot():
        return
    rows = db.query("SELECT * FROM votes WHERE status='active' AND type LIKE 'appeal%'")
    for v in rows:
        if v["deadline"] and v["deadline"] <= db.now():
            await services.resolve_vote(v["id"], forced=True)
