from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import database as db


def fmt_name(u):
    if not u:
        return "?"
    return u.get("name") or f"id{u['id']}"


def user_line(u):
    name = fmt_name(u)
    role = config.ROLE_NAMES.get(u["role"], "?")
    status = config.STATUS_NAMES.get(u["status"], u["status"])
    return f"{name} (id {u['id']}) — {role}, {status}, {u['points']:.1f} баллов"


def local_now(tz_name):
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now(ZoneInfo("Europe/Moscow"))


def parse_dt(s, fmt="%Y-%m-%d %H:%M"):
    for f in (fmt, "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), f)
        except Exception:
            pass
    return None


def parse_time(s):
    for f in ("%H:%M", "%H:%M:%S"):
        try:
            datetime.strptime(s.strip(), f)
            return s.strip()
        except Exception:
            pass
    return None


def fmt_dt(s):
    if not s:
        return "—"
    return s


def file_list_from_message(msg):
    files = []
    if msg.photo:
        files.append({"type": "photo", "id": msg.photo[-1].file_id})
    if msg.document:
        files.append({"type": "document", "id": msg.document.file_id})
    if msg.video:
        files.append({"type": "video", "id": msg.video.file_id})
    if msg.audio:
        files.append({"type": "audio", "id": msg.audio.file_id})
    if msg.animation:
        files.append({"type": "animation", "id": msg.animation.file_id})
    return files


def extract_files(row):
    return db.jload(row.get("files") if isinstance(row, dict) else row, [])


async def send_content(bot, chat_id, text, photo=None, files=None, kb=None,
                       thread=None, warn=True):
    files = files or []
    try:
        if photo:
            if files:
                media = [{"type": "photo", "media": photo, "caption": text or ""}]
                for f in files[:9]:
                    t = "photo" if f["type"] in ("photo", "animation") else f["type"]
                    media.append({"type": t, "media": f["id"]})
                await bot.send_media_group(chat_id, media, message_thread_id=thread)
                if kb:
                    await bot.send_message(chat_id, "⬆️ Вложение", reply_markup=kb,
                                           message_thread_id=thread)
                return True
            await bot.send_photo(chat_id, photo, caption=text, reply_markup=kb,
                                 message_thread_id=thread)
            return True
        if files:
            if len(files) == 1:
                f = files[0]
                if f["type"] == "photo":
                    await bot.send_photo(chat_id, f["id"], caption=text, reply_markup=kb,
                                         message_thread_id=thread)
                elif f["type"] == "document":
                    await bot.send_document(chat_id, f["id"], caption=text, reply_markup=kb,
                                            message_thread_id=thread)
                elif f["type"] == "video":
                    await bot.send_video(chat_id, f["id"], caption=text, reply_markup=kb,
                                         message_thread_id=thread)
                elif f["type"] == "audio":
                    await bot.send_audio(chat_id, f["id"], caption=text, reply_markup=kb,
                                         message_thread_id=thread)
                else:
                    await bot.send_message(chat_id, text or "Вложение", reply_markup=kb,
                                           message_thread_id=thread)
                return True
            media = []
            for i, f in enumerate(files[:9]):
                t = "photo" if f["type"] in ("photo", "animation") else f["type"]
                item = {"type": t, "media": f["id"]}
                if i == 0 and text:
                    item["caption"] = text
                media.append(item)
            await bot.send_media_group(chat_id, media, message_thread_id=thread)
            if kb:
                await bot.send_message(chat_id, "⬆️ Вложения", reply_markup=kb,
                                       message_thread_id=thread)
            return True
        await bot.send_message(chat_id, text, reply_markup=kb, message_thread_id=thread)
        return True
    except Exception as e:
        if warn:
            try:
                await bot.send_message(chat_id, f"⚠️ Ошибка отправки: {e}")
            except Exception:
                pass
        return False


def kb(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
                         for row in rows]
    )


def back_kb(to="menu"):
    return kb([["⬅️ Назад", f"back:{to}"]])


SUPPORT_PHRASES = [
    "Отличная работа — так держать! 💪",
    "Класс! Проект становится лучше благодаря тебе. 🚀",
    "Молодец, продолжай в том же духе! ⭐",
    "Хорошая работа, видно усердие. 👏",
    "Спасибо за вклад в проект! ❤️",
]


def support_phrase():
    import random
    return random.choice(SUPPORT_PHRASES)
