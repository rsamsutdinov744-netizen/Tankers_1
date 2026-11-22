import os

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
             or os.getenv("TELEGRAM_TOKEN") or os.getenv("TOKEN")
             or "ВСТАВЬТЕ_СВОЙ_ТОКЕН")

DEFAULT_PASSWORDS = {
    "pw_user":  "UT653IO212",
    "pw_admin": "Admin5642iS2",
    "pw_owner": "Admin 5642iS25612#",
}

ROLE_NAMES = {
    0: "Участник",
    1: "Админ младший",
    2: "Админ средний",
    3: "Админ старший",
    4: "Владелец",
}

POSITIONS = {
    "artist":   "🎨 Художник",
    "writer":   "✍️ Сценарист",
    "animator": "🎬 Аниматор",
    "helper":   "🧰 Помощник",
}

STATUS_NAMES = {
    "newbie":    "🔵 Новичок",
    "member":    "🟢 Участник",
    "best":      "🟡 Лучший участник",
    "lead":      "🟣 Ведущий",
    "candidate": "📌 Кандидат",
    "owner":     "🔴 Владелец",
}

RESULT_POINTS = {
    "❌ Совсем неверно": 0,
    "🔴 Неправильно":   1,
    "🟡 Частично верно": 3,
    "🟢 Правильно":     5,
}

PUNISH_KINDS = {
    "warning":  "⚠️ Предупреждение",
    "points":   "➖ Минус баллы",
    "monthly":  "📊 Отчёт за месяц",
    "search":   "🔎 Поиск информации",
    "custom":   "✏️ Своё задание",
}

GROUP_TYPES = {
    "task":         "📋 Задания",
    "reminder":     "⏰ Напоминания",
    "material":     "📚 Материалы",
    "announcement": "📢 Объявления",
    "checklist":    "✅ Чек-листы",
}

RIGHTS = [
    ("tasks",        "Задания"),
    ("checklists",   "Чек-листы"),
    ("punishments",  "Наказания"),
    ("works",        "Работы"),
    ("materials",    "Материалы"),
    ("announcements","Объявления"),
    ("reminders",    "Напоминания"),
    ("curators",     "Кураторы"),
    ("publish",      "Место публикации"),
    ("stats",        "Статистика"),
    ("trash",        "Корзина и архив"),
    ("search",       "Поиск участников"),
    ("logs",         "История действий"),
    ("export",       "Экспорт CSV"),
    ("bans",         "Баны"),
    ("templates",    "Шаблоны"),
    ("passwords",    "Пароли"),
    ("roles",        "Роли"),
    ("delete_users", "Удаление участников"),
]

DEFAULT_RIGHTS = {
    1: ["tasks", "works", "materials", "announcements"],
    2: ["tasks", "works", "materials", "announcements", "checklists",
        "punishments", "reminders", "curators", "stats", "templates"],
    3: ["tasks", "works", "materials", "announcements", "checklists",
        "punishments", "reminders", "curators", "stats", "templates",
        "publish", "trash", "search", "logs", "export", "bans"],
    4: [r[0] for r in RIGHTS],
}

PROMOTE_BEST = 75
PROMOTE_LEAD = 140

TRASH_HOURS = 48
PUNISH_GRACE_DAYS = 3
PUNISH_FINE_PER_DAY = 8
CHECKLIST_LIE_FINE = 10
CHECKLIST_WRONG_CHECK_FINE = 7
