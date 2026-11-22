from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import POSITIONS, RIGHTS, GROUP_TYPES


def rkb(rows, resize=True):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b) for b in row] for row in rows],
        resize_keyboard=resize,
    )


def main_menu(u):
    try:
        role = int(u["role"])
    except (TypeError, ValueError, KeyError):
        role = 0
    rows = [
        ["📋 Задания", "📚 Материалы", "📢 Объявления"],
        ["📤 Мои работы", "👤 Профиль", "💼 Должность"],
        ["🏠 Меню"],
    ]
    if role >= 1:
        rows.append(["🛠 Админ-панель"])
    if role >= 4:
        rows.append(["⚙️ Владелец"])
    return rkb(rows)


def pos_kb(back_cb="menu"):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = [[InlineKeyboardButton(text=name, callback_data=f"pos:{key}")]
            for key, name in POSITIONS.items()]
    rows.append([InlineKeyboardButton(text="❌ Без должности", callback_data="pos:none")])
    from utils import kb
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yes_no(prefix):
    from utils import kb
    return kb([[["✅ Да", f"{prefix}:yes"], ["❌ Нет", f"{prefix}:no"]]])
