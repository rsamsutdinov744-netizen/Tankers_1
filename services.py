import asyncio
import json
from datetime import datetime, timedelta

import config
import database as db
from utils import send_content, kb, user_line, local_now, fmt_name

bot_ref = None


def set_bot(b):
    global bot_ref
    bot_ref = b


def get_bot():
    return bot_ref


def owners_ids():
    rows = db.query("SELECT id FROM users WHERE role>=4 AND banned=0 AND leave_at IS NULL")
    return [r["id"] for r in rows]


def curators_for_pos(pos):
    if not pos:
        return owners_ids()
    rows = db.query(
        "SELECT c.user_id FROM curators c JOIN users u ON u.id=c.user_id "
        "WHERE c.pos=? AND u.banned=0 AND u.leave_at IS NULL", (pos,))
    ids = [r["user_id"] for r in rows]
    for oid in owners_ids():
        if oid not in ids:
            ids.append(oid)
    return ids


async def notify(uid, text, photo=None, files=None, kbd=None, thread=None):
    if not bot_ref:
        return
    await send_content(bot_ref, uid, text, photo, files, kbd, thread)


async def notify_admins_with_right(right, text, photo=None, files=None, kbd=None):
    rows = db.query(
        "SELECT * FROM users WHERE role>=1 AND banned=0 AND leave_at IS NULL "
        "ORDER BY role DESC")
    for u in rows:
        if u["role"] >= 4 or db.has_right(u, right):
            await notify(u["id"], text, photo, files, kbd)


def log(uid, action, details=""):
    db.log_action(uid, action, details)


async def publish(bot, gtype, text, photo=None, files=None, kbd=None, thread=None):
    groups = db.query("SELECT * FROM groups WHERE type=? AND is_permanent=1", (gtype,))
    ok = 0
    for g in groups:
        t = thread if thread is not None else g["thread_id"]
        if await send_content(bot, g["chat_id"], text, photo, files, kbd, t, warn=False):
            ok += 1
    return ok


def vote_approvers(vtype, target):
    u = db.get_user(target)
    if not u:
        return owners_ids()
    if vtype in ("best", "lead"):
        return curators_for_pos(u["pos"])
    return []


def create_vote(vtype, target_id, reason=""):
    existing = db.get(
        "SELECT id FROM votes WHERE type=? AND target_id=? AND status='active'",
        (vtype, target_id))
    if existing:
        return None
    vid = db.execute(
        "INSERT INTO votes(type,target_id,status,deadline,reason,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (vtype, target_id, "active",
         (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
         reason, db.now()))
    return vid


async def vote_cast(vid, voter_id, choice, weight=None):
    if weight is None:
        v = db.get_user(voter_id)
        weight = 1 if v and v["status"] == "newbie" else 2
    db.execute(
        "INSERT OR REPLACE INTO vote_records(vote_id,voter_id,weight,choice) VALUES(?,?,?,?)",
        (vid, voter_id, weight, choice))
    vote = db.get("SELECT * FROM votes WHERE id=?", (vid,))
    if not vote or vote["status"] != "active":
        return
    vtype = vote["type"]
    if vtype in ("best", "lead"):
        approvers = vote_approvers(vtype, vote["target_id"])
        recs = db.query("SELECT voter_id FROM vote_records WHERE vote_id=?", (vid,))
        if all(r["voter_id"] in [x["voter_id"] for x in recs] for r in
               [{"voter_id": a} for a in approvers]):
            await resolve_vote(vid)
    else:
        pass


async def vote_finish(vid):
    vote = db.get("SELECT * FROM votes WHERE id=?", (vid,))
    if not vote or vote["status"] != "active":
        return
    vtype = vote["type"]
    if vtype in ("best", "lead"):
        approvers = vote_approvers(vtype, vote["target_id"])
        recs = db.query("SELECT voter_id FROM vote_records WHERE vote_id=?", (vid,))
        voters = [r["voter_id"] for r in recs]
        if all(a in voters for a in approvers):
            await resolve_vote(vid)


async def resolve_vote(vid, forced=False):
    vote = db.get("SELECT * FROM votes WHERE id=?", (vid,))
    if not vote or vote["status"] != "active":
        return
    vtype, target = vote["type"], vote["target_id"]
    user = db.get_user(target)
    recs = db.query("SELECT * FROM vote_records WHERE vote_id=?", (vid,))
    yes = sum(r["weight"] for r in recs if r["choice"] == "yes")
    no = sum(r["weight"] for r in recs if r["choice"] == "no")
    approvers = vote_approvers(vtype, target) if vtype in ("best", "lead") else None

    db.execute("UPDATE votes SET status='closed' WHERE id=?", (vid,))

    if vtype in ("best", "lead") and not forced:
        if any(a not in [r["voter_id"] for r in recs] for a in approvers):
            return
        all_yes = len(recs) == len([a for a in approvers]) and all(
            r["choice"] == "yes" for r in recs)
        new_status = "best" if vtype == "best" else "lead"
        if all_yes and user:
            db.execute("UPDATE users SET status=? WHERE id=?", (new_status, target))
            await notify(target, f"🎉 Справедливое решение: вам присвоен статус "
                                 f"{config.STATUS_NAMES[new_status]}!")
            db.log_system("promote", f"{target} -> {new_status}")
        else:
            await notify(target, "❌ Справедливое решение: в повышении отказано."
                                 "\nВы можете подать апелляцию — все участники проголосуют.")
    elif vtype.startswith("appeal"):
        total = sum(r["weight"] for r in recs)
        base = target_base_status(vtype)
        if total == 0:
            return
        if yes * 2 >= total:
            db.execute("UPDATE users SET status=? WHERE id=?", (base, target))
            await notify(target, f"🎉 Апелляция выиграна! Вам присвоен статус "
                                 f"{config.STATUS_NAMES[base]}.")
            db.log_system("appeal_win", f"{target} -> {base}")
            return
        if vtype.endswith("appeal1"):
            await notify(target, "❌ Первая апелляция отклонена. "
                                 "Вы можете подать вторую (финальную) апелляцию.")
        else:
            db.execute("UPDATE users SET status=? WHERE id=?", (base, target))
            await notify(target, "⚖️ Вторая апелляция отклонена — по правилам проекта "
                                 "вам присваивается статус в 100% порядке.")
        db.log_system("appeal", f"{target} {vtype}: за {yes}, против {no}")
    elif vtype == "lead_poll":
        total = sum(r["weight"] for r in recs)
        user = db.get_user(target)
        if total and user and yes * 2 >= total:
            db.execute("UPDATE users SET status='lead' WHERE id=?", (target,))
            await notify(target, "🟣 Вы избраны ведущим по итогам опроса кандидатов!")


def target_base_status(vtype):
    return "best" if vtype.startswith("best_") else "lead"


async def check_promotions(uid):
    u = db.get_user(uid)
    if not u or u["banned"] or u["leave_at"]:
        return
    if u["status"] not in ("member", "best"):
        return
    pts = u["points"]
    if u["status"] == "member" and pts >= config.PROMOTE_BEST:
        vid = create_vote("best", uid)
        if vid:
            txt = (f"⚖️ Справедливое решение: {user_line(u)}\n"
                   f"Набрано {pts:.0f}/{config.PROMOTE_BEST} баллов.\n"
                   f"Голосуйте за повышение до «Лучший участник».")
            kbd = kb([[["✅ Повысить", f"vote:{vid}:yes"], ["❌ Против", f"vote:{vid}:no"]]])
            await notify(uid, "⚖️ Ваша кандидатура отправлена на справедливое решение:")
            for aid in vote_approvers("best", uid):
                await notify(aid, txt, kbd=kbd)
    elif u["status"] == "best" and pts >= config.PROMOTE_LEAD:
        leads = db.query("SELECT id FROM users WHERE status='lead' AND pos=? AND leave_at IS NULL",
                         (u["pos"],))
        if not leads:
            vid = create_vote("lead", uid)
            if vid:
                txt = (f"⚖️ Справедливое решение: {user_line(u)}\n"
                       f"Набрано {pts:.0f}/{config.PROMOTE_LEAD} баллов.\n"
                       f"Голосуйте за повышение до «Ведущий».")
                kbd = kb([[["✅ Повысить", f"vote:{vid}:yes"], ["❌ Против", f"vote:{vid}:no"]]])
                for aid in vote_approvers("lead", uid):
                    await notify(aid, txt, kbd=kbd)
        else:
            cand = db.jload(db.setting("candidates", "[]"))
            if uid not in cand:
                cand.append(uid)
                db.set_setting("candidates", json.dumps(cand))
                await notify(uid, "📌 Все места ведущих заняты — вы добавлены в список кандидатов.")


async def add_points(uid, delta, reason=""):
    u = db.get_user(uid)
    if not u:
        return
    new_pts = max(0.0, u["points"] + delta)
    db.execute("UPDATE users SET points=? WHERE id=?", (new_pts, uid))
    db.log_action(uid, "points", f"{delta:+} ({reason})")
    if delta > 0:
        await check_promotions(uid)


def start_lead_poll(left_lead_pos):
    cand = db.jload(db.setting("candidates", "[]"))
    cand = [c for c in cand if (db.get_user(c) or {}).get("status") in ("best", "candidate")]
    if not cand:
        return None
    target = cand[0]
    vid = create_vote("lead_poll", target)
    if vid:
        db.set_setting("candidates", json.dumps([c for c in cand if c != target]))
    return vid


async def weekly_report_job():
    if not bot_ref:
        return
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    lines = ["📊 Еженедельный отчёт по проекту\n"]
    new_users = db.query("SELECT * FROM users WHERE created_at>=?", (week_ago,))
    lines.append(f"🆕 Новые участники: {len(new_users)}")
    left = db.query("SELECT * FROM users WHERE leave_at>=? AND leave_at IS NOT NULL", (week_ago,))
    lines.append(f"👋 Ушли: {len(left)}")
    act = db.query(
        "SELECT w.user_id, COUNT(*) c FROM works w WHERE w.created_at>=? GROUP BY w.user_id "
        "ORDER BY c DESC", (week_ago,))
    if act:
        top = db.get_user(act[0]["user_id"])
        lines.append(f"🏆 Самый активный: {fmt_name(top)} — {act[0]['c']} работ")
        lazy = [r["user_id"] for r in db.query(
            "SELECT id FROM users WHERE role=0 AND banned=0 AND leave_at IS NULL "
            "AND created_at<?", (week_ago,)) if r["id"] not in [a["user_id"] for a in act]]
        if lazy:
            names = ", ".join(fmt_name(db.get_user(i)) for i in lazy[:10])
            lines.append(f"💤 Без работ за неделю: {names}")
    gr = db.get("SELECT AVG(grade) g, COUNT(*) c FROM works WHERE reviewed_at>=? AND grade>0",
                (week_ago,))
    if gr and gr["c"]:
        lines.append(f"📈 Средняя оценка работ: {gr['g']:.1f} (работ: {gr['c']})")
    text = "\n".join(lines)
    await publish(bot_ref, "announcement", text)
    await notify_admins_with_right("stats", text)


async def auto_analysis_job():
    if not bot_ref:
        return
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    lines = ["🤖 Автоматический анализ\n"]
    active_ids = [r["user_id"] for r in db.query(
        "SELECT DISTINCT user_id FROM works WHERE created_at>=?", (week_ago,))]
    no_works = [u for u in db.query(
        "SELECT * FROM users WHERE role=0 AND banned=0 AND leave_at IS NULL")
        if u["id"] not in active_ids]
    if no_works:
        lines.append(f"💤 Без работ за неделю: "
                     + ", ".join(fmt_name(u) for u in no_works[:15]))
    low = db.query(
        "SELECT user_id, AVG(grade) g FROM works WHERE reviewed_at>=? GROUP BY user_id "
        "HAVING g<4", (week_ago,))
    for r in low:
        u = db.get_user(r["user_id"])
        if u:
            lines.append(f"⚠️ Низкая оценка ({r['g']:.1f}): {fmt_name(u)}")
    stale = db.query(
        "SELECT * FROM tasks WHERE status='active' AND created_at<=?",
        ((datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),))
    for t in stale:
        has_work = db.get("SELECT id FROM works WHERE task_id=? AND created_at>=?", 
                          (t["id"], (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")))
        if not has_work:
            lines.append(f"⛔ Задание #{t['id']} без движения более 3 дней")
    if len(lines) == 1:
        return
    for oid in owners_ids():
        await notify(oid, "\n".join(lines))


async def trash_tick():
    limit = (datetime.now() - timedelta(hours=config.TRASH_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("DELETE FROM trash WHERE deleted_at<=?", (limit,))


async def punish_tick():
    if not bot_ref:
        return
    today = datetime.now()
    rows = db.query("SELECT * FROM punishments WHERE status IN ('active','submitted')")
    for p in rows:
        dl = p["deadline"]
        if not dl:
            continue
        try:
            ddl = datetime.strptime(dl, "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                ddl = datetime.strptime(dl, "%Y-%m-%d")
            except Exception:
                continue
        grace_end = ddl + timedelta(days=config.PUNISH_GRACE_DAYS)
        if today >= grace_end and p["kind"] != "warning":
            fined_before = p["fined_days"] or 0
            days_over = (today.date() - grace_end.date()).days + 1
            if days_over > fined_before:
                db.execute("UPDATE punishments SET fined_days=? WHERE id=?",
                           (days_over, p["id"]))
                await add_points(p["user_id"], -config.PUNISH_FINE_PER_DAY,
                                 f"просрочка наказания #{p['id']}")
                if days_over == fined_before + 1:
                    await notify(p["user_id"],
                                 f"⏰ Просрочен отчёт по наказанию #{p['id']}. "
                                 f"Штраф −{config.PUNISH_FINE_PER_DAY} баллов в день!")
                await notify_admins_with_right("punishments",
                    f"⏰ {fmt_name(db.get_user(p['user_id']))} просрочил наказание "
                    f"#{p['id']} (штраф день {days_over}).")


async def reminders_tick():
    if not bot_ref:
        return
    rows = db.query("SELECT * FROM reminders WHERE active=1")
    now_utc = datetime.utcnow()
    for r in rows:
        kind = r["kind"]
        if kind == "once":
            dt = parse_any(r["time"])
            if dt and not r["fired"] and now_utc + timedelta(hours=3) >= dt:
                await fire_reminder(r)
                db.execute("UPDATE reminders SET fired=1, active=0 WHERE id=?", (r["id"],))
        elif kind == "daily":
            sent_key = f"rem:{r['id']}:{now_utc.strftime('%Y-%m-%d')}"
            if not db.setting(sent_key):
                time_h, time_m = (r["time"] or "17:00").split(":")[:2]
                if (now_utc + timedelta(hours=3)).strftime("%H:%M") == f"{time_h}:{time_m}":
                    await fire_reminder(r)
                    db.set_setting(sent_key, "1")
        elif kind == "weekly":
            days = db.jload(r["weekly"], [])
            msk_now = now_utc + timedelta(hours=3)
            if str(msk_now.isoweekday()) in [str(d) for d in days]:
                sent_key = f"rem:{r['id']}:{msk_now.strftime('%Y-%m-%d')}"
                if not db.setting(sent_key):
                    time_h, time_m = (r["time"] or "17:00").split(":")[:2]
                    if msk_now.strftime("%H:%M") == f"{time_h}:{time_m}":
                        await fire_reminder(r)
                        db.set_setting(sent_key, "1")
        elif kind == "dates":
            dates = db.jload(r["dates"], [])
            msk_date = (now_utc + timedelta(hours=3)).strftime("%Y-%m-%d")
            if msk_date in [str(d) for d in dates]:
                sent_key = f"rem:{r['id']}:{msk_date}"
                if not db.setting(sent_key):
                    time_h, time_m = (r["time"] or "17:00").split(":")[:2]
                    if (now_utc + timedelta(hours=3)).strftime("%H:%M") == f"{time_h}:{time_m}":
                        await fire_reminder(r)
                        db.set_setting(sent_key, "1")


def parse_any(s):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


async def fire_reminder(r):
    if not bot_ref:
        return
    dm_users = db.jload(r["dm_users"], None)
    if dm_users:
        for item in dm_users:
            uid = item["uid"]
            tz = item.get("timezone") or "Europe/Moscow"
            local = local_now(tz)
            want = item.get("time")
            if want:
                if local.strftime("%H:%M") != want:
                    continue
            await send_content(bot_ref, uid, f"⏰ Напоминание:\n{r['text']}",
                               r["photo"], warn=False)
    else:
        await publish(bot_ref, "reminder", f"⏰ Напоминание:\n{r['text']}",
                      r["photo"], thread=r["thread"])
    db.log_system("reminder_fired", str(r["id"]))


def scheduler_jobs(sched):
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    sched.add_job(reminders_tick, IntervalTrigger(seconds=30), id="reminders")
    sched.add_job(punish_tick, IntervalTrigger(hours=1), id="punish")
    sched.add_job(trash_tick, IntervalTrigger(minutes=30), id="trash")
    sched.add_job(weekly_report_job, CronTrigger(day_of_week="mon", hour=10, minute=0),
                  id="weekly")
    sched.add_job(auto_analysis_job, CronTrigger(hour=9, minute=0), id="analysis")
