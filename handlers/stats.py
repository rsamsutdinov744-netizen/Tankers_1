import csv
import io
import json
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile

import config
import database as db
import services
from utils import kb, fmt_name

router = Router()


@router.message(F.text == "📊 Статистика")
async def stats_menu(m: Message, state: FSMContext):
    u = db.get_user(m.from_user.id)
    if not u:
        return
    await state.clear()
    rows = [["📊 Моя неделя", "st:me"], ["⬅️ Назад", "back:menu"]]
    if db.has_right(u, "stats"):
        rows.insert(0, ["📈 Отчёт по проекту", "st:project"])
        rows.insert(1, ["🤖 Автоанализ", "st:analysis"])
        rows.insert(2, ["🏆 Лучшие/худшие", "st:top"],)
    await m.answer("📊 Статистика:", reply_markup=kb(rows))


@router.callback_query(F.data.startswith("st:me"))
async def st_me(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    pts = db.get("SELECT COALESCE(SUM(points),0) s FROM works WHERE user_id=? AND "
                 "reviewed_at>=?", (u["id"], week_ago))["s"]
    done = db.get("SELECT COUNT(*) c FROM works WHERE user_id=? AND status='reviewed' AND "
                  "reviewed_at>=?", (u["id"], week_ago))["c"]
    fails = db.get("SELECT COUNT(*) c FROM punishments WHERE user_id=? AND created_at>=?",
                   (u["id"], week_ago))["c"]
    cl_done = db.get("SELECT COUNT(*) c FROM checklist_items WHERE taker_id=? AND "
                     "status='checked' AND checked_at>=?", (u["id"], week_ago))["c"]
    text = (f"📊 Ваша статистика за неделю:\n\n"
            f"Баллов за неделю: {pts:.1f}\n"
            f"Выполнено заданий: {done}\n"
            f"Выполнено пунктов чек-листов: {cl_done}\n"
            f"Наказаний: {fails}\n"
            f"Всего баллов: {u['points']:.1f}")
    await c.message.answer(text)
    await c.answer()


@router.callback_query(F.data.startswith("st:project"))
async def st_project(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "stats"):
        await c.answer("Нет прав", show_alert=True)
        return
    week_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    new_users = db.get("SELECT COUNT(*) c FROM users WHERE created_at>=?",
                       (week_ago,))["c"]
    left = db.get("SELECT COUNT(*) c FROM users WHERE leave_at IS NOT NULL AND leave_at>=?",
                  (week_ago,))["c"]
    act = db.query("SELECT user_id, COUNT(*) c FROM works WHERE created_at>=? "
                   "GROUP BY user_id ORDER BY c DESC", (week_ago,))
    top_line = "—"
    if act:
        top = db.get_user(act[0]["user_id"])
        top_line = f"{fmt_name(top)} ({act[0]['c']} работ)"
    idle = []
    all_users = db.query("SELECT * FROM users WHERE role=0 AND banned=0 AND leave_at IS NULL")
    active = {a["user_id"] for a in act}
    idle = [u2 for u2 in all_users if u2["id"] not in active]
    avg_grade = db.get("SELECT AVG(grade) g FROM works WHERE reviewed_at>=? AND grade>0",
                       (week_ago,))["g"] or 0
    avg_pts = db.get("SELECT AVG(points) p FROM users WHERE role=0 AND leave_at IS NULL")["p"] or 0
    cur_lines = []
    for cu in db.query("SELECT * FROM users WHERE role>=1 AND leave_at IS NULL"):
        cnt = db.get("SELECT COUNT(*) c FROM works WHERE reviewer_id=? AND reviewed_at>=?",
                     (cu["id"], week_ago))["c"]
        cur_lines.append(f"🧑‍🏫 {fmt_name(cu)} — проверок: {cnt}")
    cur_lines.sort(key=lambda s: -int(s.split(":")[-1]) if s.split(":")[-1].strip().isdigit()
                   else 0)
    text = (f"📈 Отчёт по проекту (30 дней)\n\n"
            f"🆕 Новые участники: {new_users}\n"
            f"👋 Ушедшие: {left}\n"
            f"🏆 Самый активный: {top_line}\n"
            f"✅ Средняя оценка работ: {avg_grade:.1f}/10\n"
            f"📊 Средний балл участников: {avg_pts:.1f}\n\n"
            f"💤 Не работают: " + (", ".join(fmt_name(x) for x in idle[:10]) or "—") + "\n\n"
            f"🧑‍🏫 Кураторы:\n" + "\n".join(cur_lines[:8] if cur_lines else ["—"]))
    await c.message.answer(text)
    await c.answer()


@router.callback_query(F.data.startswith("st:analysis"))
async def st_analysis(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "stats"):
        await c.answer("Нет прав", show_alert=True)
        return
    await services.auto_analysis_job()
    await c.answer("Анализ запущен — отчёт придёт владельцу")


@router.callback_query(F.data.startswith("st:top"))
async def st_top(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "stats"):
        await c.answer("Нет прав", show_alert=True)
        return
    best = db.query("SELECT * FROM users WHERE role=0 AND leave_at IS NULL "
                    "ORDER BY points DESC LIMIT 5")
    worst = db.query("SELECT * FROM users WHERE role=0 AND leave_at IS NULL "
                     "ORDER BY points ASC LIMIT 5")
    text = "🏆 Лучшие:\n" + "\n".join(f"{i+1}. {fmt_name(x)} — {x['points']:.1f}"
                                      for i, x in enumerate(best))
    text += "\n\n💤 Самые низкие баллы:\n" + "\n".join(
        f"{i+1}. {fmt_name(x)} — {x['points']:.1f}" for i, x in enumerate(worst))
    await c.message.answer(text)
    await c.answer()


async def export_table(title, rows, cols):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(col) for col in cols])
    return BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=title)


@router.message(F.text == "📤 Экспорт CSV")
async def export_menu(m: Message):
    u = db.get_user(m.from_user.id)
    if not db.has_right(u, "export"):
        return
    await m.answer("📤 Что экспортировать?", reply_markup=kb([
        ["👥 Участники", "csv:users"], ["📤 Работы", "csv:works"],
        ["📜 Логи", "csv:logs"], ["⬅️ Назад", "back:menu"]]))


@router.callback_query(F.data.startswith("csv:"))
async def csv_export(c: CallbackQuery):
    u = db.get_user(c.from_user.id)
    if not db.has_right(u, "export"):
        await c.answer("Нет прав", show_alert=True)
        return
    which = c.data.split(":")[1]
    if which == "users":
        rows = db.query("SELECT * FROM users")
        cols = ["id", "name", "role", "admin_level", "pos", "status", "points", "banned",
                "timezone", "created_at"]
        fname = "users.csv"
    elif which == "works":
        rows = db.query("SELECT * FROM works")
        cols = ["id", "task_id", "user_id", "kind", "status", "grade", "result", "points",
                "reviewer_id", "created_at", "reviewed_at"]
        fname = "works.csv"
    else:
        rows = db.query("SELECT * FROM logs ORDER BY id DESC LIMIT 5000")
        cols = ["id", "user_id", "action", "details", "ts"]
        fname = "logs.csv"
    file = await export_table(fname, rows, cols)
    await c.bot.send_document(c.from_user.id, file)
    services.log(c.from_user.id, "csv_export", which)
    await c.answer("Готово")
