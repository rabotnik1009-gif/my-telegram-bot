import os
import logging
import time
from datetime import datetime, timedelta
import pytz
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# Создаем Flask сервер
app = Flask('')

@app.route('/')
def home():
    return "🤖 Telegram Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Запускаем сервер в отдельном потоке, чтобы не мешать боту
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()
print("✅ Встроенный веб-сервер запущен на порту 8080")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# Расписание уроков по дням недели (0-понедельник, 1-вторник...)
SCHEDULE = {
    0: [  # Понедельник
        "Труды / 30", "Труды / 30", "Физика / 26", "История Беларуси / 23",
        "Бел. Лит / 29", "География / 24"
    ],
    1: [  # Вторник
        "Биология / 22", "Информатика / 11", "Физкультура / сп. зал",
        "Алгебра / 16", "Немецкий язык / 20", "Физика / 32", "Астрономия / 32"
    ],
    2: [  # Среда
        "Труды / 30", "Труды / 30", "Алгебра / 32", "Русская литература / 29",
        "Русский язык / 29", "Химия / 28", "Общество / 10"
    ],
    3: [  # Четверг
        "Физкультура / сп. зал", "Труды / 30", "Труды / 30", "Бел. Лит / 27",
        "Бел. Яз / 27", "Геометрия / 24", "Физкультура / сп. зал"
    ],
    4: [  # Пятница
        "Русский язык / 29", "Биология / 22", "История Беларуси / 23",
        "Физкультура / сп. зал", "Геометрия / 24", "Немецкий Язык / 20",
        "Химия / 28"
    ],
    5: [],  # Суббота - нет уроков
    6: []  # Воскресенье - нет уроков
}

# Названия дней недели
DAY_NAMES = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресеньe"
}

# Эмодзи для дней недели
DAY_EMOJIS = {
    0: "📚",  # Понедельник
    1: "📖",  # Вторник
    2: "📘",  # Среда
    3: "📗",  # Четверг
    4: "📙",  # Пятница
    5: "🎉",  # Суббота
    6: "🎉"   # Воскресенье
}

# Эмодзи для предметов (словарь)
SUBJECT_EMOJIS = {
    "Труды": "🔨",
    "Физика": "⚛️",
    "История Беларуси": "🇧🇾📜",
    "Бел. Лит": "📖🇧🇾",
    "География": "🗺️",
    "Биология": "🧬",
    "Информатика": "💻",
    "Физкультура": "🏃‍♂️",
    "Алгебра": "📐",
    "Немецкий язык": "🇩🇪",
    "Астрономия": "🌌",
    "Русская литература": "📚",
    "Русский язык": "📝",
    "Химия": "🧪",
    "Общество": "👥",
    "Бел. Яз": "✍️🇧🇾",
    "Геометрия": "📏",
    "Немецкий Язык": "🇩🇪",
}

# Часовой пояс Москвы (MSK, UTC+3)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Время начала уроков (по МСК)
LESSON_START = datetime.strptime("08:00", "%H:%M").time()
LESSON_DURATION = 45  # минут
BREAK_DURATION = 15  # минут

# Токен вашего бота
TOKEN = os.getenv("BOT_TOKEN")

# Хранение заметок пользователей (в памяти)
user_notes = {}

# Состояния пользователей для работы с заметками
USER_STATES = {}

# Система авторизации
PASSWORD = "checkerzxc"
AUTH_MAX_ATTEMPTS = 3
AUTH_BLOCK_TIME = 1800  # 30 минут в секундах

# Храним попытки входа и блокировки
auth_attempts = {}  # {user_id: attempts}
auth_blocked = {}  # {user_id: block_until_timestamp}
last_activity = {}  # {user_id: last_activity_timestamp}
AUTH_TIMEOUT = 600  # 10 минут бездействия

# Клавиатуры
# Главное меню с новым расположением кнопок (2 столбика)
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["📝 МОИ ЗАМЕТКИ"], ["⏰ Текущий урок", "➡️ Следующий урок"],
     ["📅 Расписание на завтра", "📖 Сегодняшние уроки"], ["📋 Вся неделя"],
     ["ℹ️ About • Кирюша"]],
    resize_keyboard=True)

# Меню редактирования заметок
EDIT_NOTES_KEYBOARD = ReplyKeyboardMarkup([["◀️ Назад"]], resize_keyboard=True)


def get_moscow_time():
    """Получить текущее время в Москве"""
    utc_now = datetime.now(pytz.utc)
    moscow_time = utc_now.astimezone(MOSCOW_TZ)
    return moscow_time


def get_day_schedule(day_offset=0):
    """Получить расписание для дня с учетом смещения"""
    today = get_moscow_time()
    target_date = today + timedelta(days=day_offset)
    day_of_week = target_date.weekday()

    day_name = DAY_NAMES[day_of_week]
    lessons = SCHEDULE[day_of_week]

    return day_name, lessons, target_date, day_of_week


def get_current_lesson_info():
    """Определить текущий урок или перемену"""
    now = get_moscow_time()
    current_time = now.time()

    # Получаем время начала дня (8:00)
    start_datetime = datetime.combine(now.date(), LESSON_START)

    # Если время до 8:00
    if current_time < LESSON_START:
        return "before_school", None, None

    # Проверяем все уроки дня
    day_of_week = now.weekday()
    lessons = SCHEDULE[day_of_week]

    if not lessons:  # Выходной
        return "weekend", None, None

    current_lesson_start = start_datetime
    lesson_number = 0

    for i in range(len(lessons)):
        lesson_start = current_lesson_start
        lesson_end = lesson_start + timedelta(minutes=LESSON_DURATION)
        break_start = lesson_end
        break_end = break_start + timedelta(minutes=BREAK_DURATION)

        # Проверяем, идет ли сейчас урок
        if lesson_start.time() <= current_time < lesson_end.time():
            return "lesson", i + 1, lessons[i]

        # Проверяем, идет ли сейчас перемена
        if lesson_end.time() <= current_time < break_end.time():
            # Если это не последняя перемена
            if i < len(lessons) - 1:
                return "break", i + 1, lessons[i + 1]
            else:
                return "after_school", None, None

        current_lesson_start = break_end
        lesson_number += 1

    return "after_school", None, None


def format_lesson_with_time(lessons):
    """Форматирование уроков с временами"""
    result = ""
    current_time = datetime.combine(datetime.now().date(), LESSON_START)

    for i, lesson in enumerate(lessons, 1):
        start_time = current_time.strftime("%H:%M")
        end_time = (current_time +
                    timedelta(minutes=LESSON_DURATION)).strftime("%H:%M")

        if " / " in lesson:
            subject, room = lesson.split(" / ")
            # Получаем соответствующий эмодзи для предмета
            emoji = SUBJECT_EMOJIS.get(subject, "📚")
            result += f"🕐 {start_time}-{end_time}\n"
            result += f"   {emoji} {subject}\n"
            result += f"   🚪{room}\n\n"
        else:
            result += f"🕐 {start_time}-{end_time}\n"
            result += f"   📚 {lesson}\n\n"

        current_time += timedelta(minutes=LESSON_DURATION + BREAK_DURATION)

    return result.strip()


def check_auth(user_id):
    """Проверяет, нужно ли запрашивать пароль"""
    now = datetime.now().timestamp()

    # Если пользователь заблокирован
    if user_id in auth_blocked:
        if now < auth_blocked[user_id]:
            return False, "blocked"
        else:
            # Блокировка истекла
            del auth_blocked[user_id]
            auth_attempts[user_id] = 0

    # Проверка тайм-аута неактивности
    if user_id in last_activity:
        if now - last_activity[user_id] > AUTH_TIMEOUT:
            # Прошло больше 10 минут, запрашиваем пароль
            return False, "timeout"

    # Если пользователь уже авторизован (была активность в пределах 10 минут)
    if user_id in last_activity and now - last_activity[user_id] <= AUTH_TIMEOUT:
        return True, "authorized"

    return False, "need_auth"


def update_activity(user_id):
    """Обновляет время последней активности пользователя"""
    last_activity[user_id] = datetime.now().timestamp()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - ВСЕГДА запрашивает пароль"""
    user = update.effective_user
    user_id = user.id

    # Сбрасываем состояние пользователя
    if user_id in USER_STATES:
        del USER_STATES[user_id]

    # ВСЕГДА проверяем блокировку первым делом
    if user_id in auth_blocked:
        block_until = auth_blocked[user_id]
        if datetime.now().timestamp() < block_until:
            remaining = int(block_until - datetime.now().timestamp())
            minutes = remaining // 60
            seconds = remaining % 60

            await update.message.reply_text(
                f"🚫 Вы заблокированы!\n"
                f"⏰ Блокировка продлится еще {minutes} минут {seconds} секунд",
                reply_markup=ReplyKeyboardRemove())
            return
        else:
            # Блокировка истекла
            del auth_blocked[user_id]
            auth_attempts[user_id] = 0

    # ВСЕГДА запрашиваем пароль при /start
    attempts = auth_attempts.get(user_id, 0)
    remaining = AUTH_MAX_ATTEMPTS - attempts

    # Сбрасываем активность, чтобы не было автоматического входа
    if user_id in last_activity:
        del last_activity[user_id]

    message = f"🔐 Добро пожаловать, {user.first_name}!\nДля доступа к боту введите пароль:"

    await update.message.reply_text(
        f"{message}\n"
        f"⚠️ У вас есть {remaining} попыток",
        reply_markup=ReplyKeyboardRemove())

    if user_id not in auth_attempts:
        auth_attempts[user_id] = 0

    USER_STATES[user_id] = "waiting_password"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопки"""
    user_id = update.effective_user.id
    message_text = update.message.text

    # Проверяем состояние пользователя
    user_state = USER_STATES.get(user_id, "main")

    # Если это кнопка "Назад" - обрабатываем её в любом состоянии
    if message_text == "◀️ Назад":
        await handle_back_button(update, context)
        return

    # Проверка на команду разблокировки (регистронезависимая)
    if message_text.lower() == "сними её нахуй":
        if user_id in auth_blocked:
            del auth_blocked[user_id]
            auth_attempts[user_id] = 0
            await update.message.reply_text(
                "✅ Блокировка снята!\n"
                "🔄 Попытки сброшены.\n"
                "🔐 Теперь введите пароль:",
                reply_markup=ReplyKeyboardRemove())
            USER_STATES[user_id] = "waiting_password"
        else:
            await update.message.reply_text("❌ Вы не заблокированы.",
                                            reply_markup=ReplyKeyboardRemove())
        return

    # Обработка ввода пароля
    if user_state == "waiting_password":
        await handle_password_input(update, context)
        return

    # Обработка разных состояний
    if user_state == "waiting_new_note":
        await save_new_note(update, context)
        return
    elif user_state == "waiting_add_to_note":
        await add_to_note(update, context)
        return
    elif user_state == "notes_menu":
        await handle_notes_menu(update, context)
        return

    # Сначала проверяем авторизацию для любого сообщения
    is_auth, reason = check_auth(user_id)
    if not is_auth:
        if reason == "blocked":
            block_until = auth_blocked[user_id]
            remaining = int(block_until - datetime.now().timestamp())
            minutes = remaining // 60
            seconds = remaining % 60

            # Форматируем время блокировки
            time_str = ""
            if minutes > 0:
                time_str += f"{minutes} минут "
            time_str += f"{seconds} секунд"

            await update.message.reply_text(
                f"🚫 Вы заблокированы!\n"
                f"⏰ Блокировка продлится еще {time_str}",
                reply_markup=ReplyKeyboardRemove())
            return
        else:
            # Запрашиваем пароль
            attempts = auth_attempts.get(user_id, 0)
            remaining = AUTH_MAX_ATTEMPTS - attempts

            # Проверяем, если пользователь заблокирован, но check_auth не вернул "blocked"
            if user_id in auth_blocked:
                block_until = auth_blocked[user_id]
                if datetime.now().timestamp() < block_until:
                    remaining_time = int(block_until - datetime.now().timestamp())
                    minutes = remaining_time // 60
                    seconds = remaining_time % 60

                    time_str = ""
                    if minutes > 0:
                        time_str += f"{minutes} минут "
                    time_str += f"{seconds} секунд"

                    await update.message.reply_text(
                        f"🚫 Вы заблокированы!\n"
                        f"⏰ Блокировка продлится еще {time_str}",
                        reply_markup=ReplyKeyboardRemove())
                    return

            await update.message.reply_text(
                f"🔐 Требуется авторизация!\n"
                f"Введите пароль для доступа к боту:\n"
                f"⚠️ У вас есть {remaining} попыток",
                reply_markup=ReplyKeyboardRemove())
            USER_STATES[user_id] = "waiting_password"
            return

    # Обновляем активность
    update_activity(user_id)

    # Главное меню
    if message_text == "📝 МОИ ЗАМЕТКИ":
        await show_notes(update, context)
    elif message_text == "⏰ Текущий урок":
        await send_current_lesson(update, context)
    elif message_text == "➡️ Следующий урок":
        await send_next_lesson(update, context)
    elif message_text == "📅 Расписание на завтра":
        await send_tomorrow_schedule(update, context)
    elif message_text == "📋 Вся неделя":
        await send_week_schedule(update, context)
    elif message_text == "📖 Сегодняшние уроки":
        await send_today_lessons(update, context)
    elif message_text == "ℹ️ About • Кирюша":
        await send_about_info(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используй кнопки ниже 👇",
                                        reply_markup=MAIN_KEYBOARD)


async def handle_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода пароля"""
    user_id = update.effective_user.id
    message_text = update.message.text

    # Инициализируем счетчик попыток, если нужно
    if user_id not in auth_attempts:
        auth_attempts[user_id] = 0

    attempts = auth_attempts[user_id]

    # Пароль проверяется строго с маленькой буквы
    if message_text == "checkerzxc":
        # Успешный вход
        auth_attempts[user_id] = 0
        last_activity[user_id] = datetime.now().timestamp()
        del USER_STATES[user_id]

        await update.message.reply_text(
            "✅ Пароль верный!\n"
            "🔓 Доступ разрешен.\n\n"
            "Выберите нужную функцию:",
            reply_markup=MAIN_KEYBOARD)
    else:
        # Неверный пароль
        attempts += 1
        auth_attempts[user_id] = attempts
        remaining = AUTH_MAX_ATTEMPTS - attempts

        if attempts >= AUTH_MAX_ATTEMPTS:
            # Блокировка
            block_until = datetime.now().timestamp() + AUTH_BLOCK_TIME
            auth_blocked[user_id] = block_until
            minutes = AUTH_BLOCK_TIME // 60
            seconds = AUTH_BLOCK_TIME % 60

            time_str = f"{minutes} минут"
            if seconds > 0:
                time_str += f" {seconds} секунд"

            await update.message.reply_text(
                f"🚫 Неверный пароль! Попытки исчерпаны.\n"
                f"⏰ Вы заблокированы на {time_str}",
                reply_markup=ReplyKeyboardRemove())
            USER_STATES[user_id] = "blocked"
        else:
            await update.message.reply_text(
                f"❌ Неверный пароль!\n"
                f"⚠️ Осталось попыток: {remaining}\n"
                f"Попробуйте еще раз:",
                reply_markup=ReplyKeyboardRemove())


async def send_about_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет информацию о разработчике"""
    about_text = ("☁️ ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ\n"
                  "════════════════\n\n"
                  "💻 ᴅᴇᴠ:\n"
                  "👤 ᴋɪʀɪʟʟ\n"
                  "🖤 16 ʏ.ᴏ.\n"
                  "📍 ʜʀᴏᴅɴᴀ, ʙᴇʟᴀʀᴜꜱ\n"
                  "🎮 ᴅᴏᴛᴀ 2 ᴘʟᴀʏᴇʀ\n\n"
                  "⚙️ ꜱᴛᴀᴄᴋ:\n"
                  "🐍 ᴘʏᴛʜᴏɴ 3.11+\n"
                  "🤖 ᴘʏᴛʜᴏɴ-ᴛᴇʟᴇɢʀᴀᴍ-ʙᴏᴛ 20.0+\n\n"
                  "🗨️ ꜱᴏᴄɪᴀʟꜱ:\n"
                  "ᴛᴇʟᴇɢʀᴀᴍ - @kiritomr\n"
                  "ᴛɪᴋᴛᴏᴋ - ʙᴇᴢᴘʀɪᴄᴇʟᴀ\n"
                  "ꜱᴛᴇᴀᴍ ᴘʀᴏꜰɪʟᴇ - https://tinyurl.com/ggmarlboro\n\n"
                  "ᴠᴇʀꜱɪᴏɴ // 1.0.0 (ɢʟᴏʙᴀʟ ʀᴇʟᴇᴀꜱᴇ)\n\n"
                  "По вопросам сотрудничества и разработки: @kiritomr")

    await update.message.reply_text(about_text, reply_markup=MAIN_KEYBOARD)


async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки Назад"""
    user_id = update.effective_user.id
    user_state = USER_STATES.get(user_id, "main")

    # Возвращаемся на предыдущий уровень
    if user_state in ["waiting_new_note", "waiting_add_to_note"]:
        # Возврат в меню заметок
        USER_STATES[user_id] = "notes_menu"
        await show_notes(update, context)
    elif user_state == "notes_menu":
        # Возврат в главное меню
        del USER_STATES[user_id]
        await update.message.reply_text("Главное меню:",
                                        reply_markup=MAIN_KEYBOARD)
    else:
        # Если непонятно откуда - возвращаем в главное меню
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await update.message.reply_text("Главное меню:",
                                        reply_markup=MAIN_KEYBOARD)


async def handle_notes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик меню заметок"""
    message_text = update.message.text
    user_id = update.effective_user.id
    has_note = user_id in user_notes

    if message_text == "✏️ Новая заметка":
        USER_STATES[user_id] = "waiting_new_note"
        await update.message.reply_text(
            "🆕 Создание заметки\n\n"
            "Напиши свою новую заметку:",
            reply_markup=EDIT_NOTES_KEYBOARD)

    elif message_text == "📝 Дополнить заметку" and has_note:
        USER_STATES[user_id] = "waiting_add_to_note"
        await update.message.reply_text(
            "➕ Дополнение заметки\n\n"
            "Напиши, что хочешь добавить:",
            reply_markup=EDIT_NOTES_KEYBOARD)

    elif message_text == "🗑️ Удалить заметку" and has_note:
        # Удаление заметки
        old_note = user_notes[user_id]
        del user_notes[user_id]

        await update.message.reply_text(f"🗑️ Заметка удалена\n\n"
                                        f"Ваша заметка:\n"
                                        f"\"{old_note}\"\n\n"
                                        f"✅ была удалена.")

        # После удаления показываем меню заметок снова
        await show_notes(update, context)

    elif message_text == "◀️ Назад":
        await handle_back_button(update, context)


async def show_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать заметки пользователя"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    # Устанавливаем состояние "в меню заметок"
    USER_STATES[user_id] = "notes_menu"

    # Получаем заметку пользователя
    note = user_notes.get(user_id)
    has_note = note is not None

    # Создаем клавиатуру в зависимости от наличия заметки
    if has_note:
        notes_keyboard = ReplyKeyboardMarkup(
            [["✏️ Новая заметка", "📝 Дополнить заметку"],
             ["🗑️ Удалить заметку"], ["◀️ Назад"]],
            resize_keyboard=True)
    else:
        notes_keyboard = ReplyKeyboardMarkup(
            [["✏️ Новая заметка"], ["◀️ Назад"]], resize_keyboard=True)

    if note:
        response = f"📝 ЗАМЕТКИ {user_name}\n\n"
        response += "💭 Твоя заметка:\n\n"
        response += f"📄 {note}\n\n"
        response += "Выбери действие:"
    else:
        response = f"📝 ЗАМЕТКИ {user_name}\n\n"
        response += "📄 У тебя пока нет заметок\n\n"
        response += "✨ Это место для твоих мыслей, заданий и напоминаний!\n"
        response += "Нажми '✏️ Новая заметка', чтобы создать первую заметку."

    await update.message.reply_text(response, reply_markup=notes_keyboard)


async def save_new_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить новую заметку пользователя"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    note_text = update.message.text

    # Сохраняем новую заметку
    user_notes[user_id] = note_text

    # Возвращаем в меню заметок
    USER_STATES[user_id] = "notes_menu"

    response = f"✅ Новая заметка сохранена!\n\n"
    response += "📝 Вот твоя заметка:\n\n"
    response += f"✨ {note_text}\n\n"
    response += "Можешь дополнить её или создать новую!"

    # Создаем клавиатуру для меню заметок
    notes_keyboard = ReplyKeyboardMarkup(
        [["✏️ Новая заметка", "📝 Дополнить заметку"], ["🗑️ Удалить заметку"],
         ["◀️ Назад"]],
        resize_keyboard=True)

    await update.message.reply_text(response, reply_markup=notes_keyboard)


async def add_to_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Дополнить существующую заметку"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    additional_text = update.message.text

    # Получаем текущую заметку и добавляем новую часть
    old_note = user_notes.get(user_id, "")
    # Заменяем серый плюсик на красивый символ ✨
    new_note = f"{old_note}\n\n✨ {additional_text}"
    user_notes[user_id] = new_note

    # Возвращаем в меню заметок
    USER_STATES[user_id] = "notes_menu"

    response = f"✅ Заметка дополнена!\n\n"
    response += "📝 Обновлённая заметка:\n\n"
    response += f"✨ {new_note}\n\n"
    response += "Можешь дополнить её ещё или создать новую!"

    # Создаем клавиатуру для меню заметок
    notes_keyboard = ReplyKeyboardMarkup(
        [["✏️ Новая заметка", "📝 Дополнить заметку"], ["🗑️ Удалить заметку"],
         ["◀️ Назад"]],
        resize_keyboard=True)

    await update.message.reply_text(response, reply_markup=notes_keyboard)


async def send_current_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текущий урок"""
    status, lesson_num, lesson_info = get_current_lesson_info()
    now = get_moscow_time()

    response = "⏰ Текущий урок\n\n"

    if status == "before_school":
        response += "📅 Уроки еще не начались\n"
        response += "🕐 Первый урок в 8:00!"
    elif status == "weekend":
        response += "🎉 Сегодня выходной!\n"
        response += "💤 Можно отдохнуть"
    elif status == "lesson":
        subject, room = lesson_info.split(" / ")
        # Получаем соответствующий эмодзи для предмета
        emoji = SUBJECT_EMOJIS.get(subject, "📚")
        response += f"🔔 Сейчас идет {lesson_num}-й урок:\n\n"
        response += f"{emoji} {subject}\n"
        response += f"🚪{room}\n"
        response += f"⏱️ Продлится до {(now + timedelta(minutes=LESSON_DURATION - (now.minute % 45))).strftime('%H:%M')}"
    elif status == "break":
        subject, room = lesson_info.split(" / ")
        # Получаем соответствующий эмодзи для предмета
        emoji = SUBJECT_EMOJIS.get(subject, "📚")
        response += "🔄 Сейчас перемена\n\n"
        response += "➡️ Следующий урок:\n"
        response += f"{emoji} {subject}\n"
        response += f"🚪{room}\n"
        response += f"⏱️ Начнется в {(now + timedelta(minutes=BREAK_DURATION - (now.minute % 15))).strftime('%H:%M')}"
    elif status == "after_school":
        response += "🏫 Уроки уже закончились\n"
    else:
        response = "Не удалось определить текущий урок"

    response += f"\n\n🕐 Текущее время: {now.strftime('%H:%M')} (МСК)"
    await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)


async def send_next_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Следующий урок"""
    status, lesson_num, lesson_info = get_current_lesson_info()
    now = get_moscow_time()
    day_of_week = now.weekday()
    lessons = SCHEDULE[day_of_week]

    response = "➡️ Следующий урок\n\n"

    if status == "before_school":
        if lessons and len(lessons) > 0:
            subject, room = lessons[0].split(" / ")
            emoji = SUBJECT_EMOJIS.get(subject, "📚")
            response += "📅 Первый урок сегодня:\n\n"
            response += f"{emoji} {subject}\n"
            response += f"🚪{room}\n"
            response += f"🕐 Начнется в 8:00"
        else:
            response += "🎉 Сегодня нет уроков!\n\n"
            tomorrow_name, tomorrow_lessons, _, _ = get_day_schedule(1)
            if tomorrow_lessons and len(tomorrow_lessons) > 0:
                subject, room = tomorrow_lessons[0].split(" / ")
                emoji = SUBJECT_EMOJIS.get(subject, "📚")
                response += f"📅 Завтра ({tomorrow_name}):\n\n"
                response += f"{emoji} {subject}\n"
                response += f"🚪{room}\n"
                response += f"🕐 Начнется в 8:00"
            else:
                response += "🎉 Завтра тоже выходной!"

    elif status == "weekend":
        response += "🎉 Сегодня выходной!\n\n"
        tomorrow_name, tomorrow_lessons, _, _ = get_day_schedule(1)
        if tomorrow_lessons and len(tomorrow_lessons) > 0:
            subject, room = tomorrow_lessons[0].split(" / ")
            emoji = SUBJECT_EMOJIS.get(subject, "📚")
            response += f"📅 Завтра ({tomorrow_name}):\n\n"
            response += f"{emoji} {subject}\n"
            response += f"🚪{room}\n"
            response += f"🕐 Начнется в 8:00"
        else:
            response += "🎉 Завтра тоже выходной!"

    elif status == "lesson":
        if lesson_num < len(lessons):
            subject, room = lessons[lesson_num].split(" / ")
            emoji = SUBJECT_EMOJIS.get(subject, "📚")
            # Время начала следующего урока
            lesson_start_time = datetime.combine(
                now.date(),
                LESSON_START) + timedelta(minutes=lesson_num *
                                          (LESSON_DURATION + BREAK_DURATION))
            response += f"📅 Следующий урок ({lesson_num+1}):\n\n"
            response += f"{emoji} {subject}\n"
            response += f"🚪{room}\n"
            response += f"🕐 Начнется в {lesson_start_time.strftime('%H:%M')}"
        else:
            # Показываем первый урок завтра
            tomorrow_name, tomorrow_lessons, _, _ = get_day_schedule(1)
            if tomorrow_lessons and len(tomorrow_lessons) > 0:
                subject, room = tomorrow_lessons[0].split(" / ")
                emoji = SUBJECT_EMOJIS.get(subject, "📚")
                response += "🏫 Уроки на сегодня закончились!\n\n"
                response += f"📅 Завтра ({tomorrow_name}):\n\n"
                response += f"{emoji} {subject}\n"
                response += f"🚪{room}\n"
                response += f"🕐 Начнется в 8:00"
            else:
                response += "🏫 Уроки на сегодня закончились!\n\n"
                response += "🎉 Завтра выходной!"

    elif status == "break":
        if lesson_info:
            subject, room = lesson_info.split(" / ")
            emoji = SUBJECT_EMOJIS.get(subject, "📚")
            # Время начала следующего урока
            next_lesson_time = now + timedelta(minutes=BREAK_DURATION - (now.minute % 15))
            response += f"📅 Следующий урок ({lesson_num}):\n\n"
            response += f"{emoji} {subject}\n"
            response += f"🚪{room}\n"
            response += f"🕐 Начнется в {next_lesson_time.strftime('%H:%M')}"
        else:
            response += "🔄 Сейчас перемена\n"
            response += "⏱️ Больше уроков на сегодня нет"

    elif status == "after_school":
        tomorrow_name, tomorrow_lessons, _, _ = get_day_schedule(1)
        if tomorrow_lessons and len(tomorrow_lessons) > 0:
            subject, room = tomorrow_lessons[0].split(" / ")
            emoji = SUBJECT_EMOJIS.get(subject, "📚")
            response += f"🏫 Завтра ({tomorrow_name}):\n\n"
            response += f"{emoji} {subject}\n"
            response += f"🚪{room}\n"
            response += f"🕐 Начнется в 8:00"
        else:
            response += "🎉 Завтра выходной!\n\n"
            response += "💤 Можно отдохнуть"
    else:
        response = "Не удалось определить следующий урок"

    response += f"\n\n🕐 Текущее время: {now.strftime('%H:%M')} (МСК)"
    await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)


async def send_tomorrow_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расписание на завтра с временами"""
    day_name, lessons, date, day_num = get_day_schedule(1)
    emoji = DAY_EMOJIS[day_num]

    if not lessons:
        response = f"{emoji} {day_name} ({date.strftime('%d.%m.%Y')})\n\n"
        response += "🎉 ВЫХОДНОЙ! 🎉\n"
        response += "Можно отдохнуть от уроков!"
        await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)
        return

    response = f"{emoji} {day_name} ({date.strftime('%d.%m.%Y')})\n\n"
    response += format_lesson_with_time(lessons)

    await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)


async def send_week_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полное расписание на всю неделю"""
    today = get_moscow_time()

    response = "📚 Расписание на неделю\n\n"

    for day_num in range(7):
        day_date = today + timedelta(days=day_num)
        day_name = DAY_NAMES[day_num]
        emoji = DAY_EMOJIS[day_num]
        lessons = SCHEDULE[day_num]

        # Индикатор сегодняшнего дня
        indicator = "📍 СЕГОДНЯ" if day_num == today.weekday() else ""

        response += f"{emoji} {day_name} ({day_date.strftime('%d.%m')}) {indicator}\n"

        if not lessons:
            response += "🎉 Выходной\n\n"
        else:
            for i, lesson in enumerate(lessons):
                if " / " in lesson:
                    subject, room = lesson.split(" / ")
                    subject_emoji = SUBJECT_EMOJIS.get(subject, "📚")
                    response += f"{i+1}. {subject_emoji} {subject}\n"
                    response += f"   🚪{room}\n"
                else:
                    response += f"{i+1}. 📚 {lesson}\n"
            response += "\n"

    await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)


async def send_today_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех уроков сегодня с временами"""
    day_name, lessons, date, day_num = get_day_schedule(0)
    emoji = DAY_EMOJIS[day_num]

    response = f"📖 Сегодняшние уроки\n"
    response += f"{emoji} {day_name} ({date.strftime('%d.%m.%Y')})\n\n"

    if not lessons:
        response += "🎉 Сегодня нет уроков! Выходной! 🎉"
        await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)
        return

    current_time = datetime.combine(date.date(), LESSON_START)

    for i, lesson in enumerate(lessons, 1):
        start_time = current_time.strftime("%H:%M")
        end_time = (current_time + timedelta(minutes=LESSON_DURATION)).strftime("%H:%M")

        if " / " in lesson:
            subject, room = lesson.split(" / ")
            subject_emoji = SUBJECT_EMOJIS.get(subject, "📚")
            response += f"🔔 {i}. {subject_emoji} {subject}\n"
            response += f"   🚪{room}\n"
            response += f"   🕐 {start_time}-{end_time}\n\n"
        else:
            response += f"🔔 {i}. 📚 {lesson}\n"
            response += f"   🕐 {start_time}-{end_time}\n\n"

        current_time += timedelta(minutes=LESSON_DURATION + BREAK_DURATION)

    await update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)


async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /tomorrow"""
    await send_tomorrow_schedule(update, context)


async def now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /now"""
    await send_current_lesson(update, context)


async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /next"""
    await send_next_lesson(update, context)


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /week"""
    await send_week_schedule(update, context)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /today"""
    await send_today_lessons(update, context)


def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tomorrow", tomorrow_command))
    application.add_handler(CommandHandler("now", now_command))
    application.add_handler(CommandHandler("next", next_command))
    application.add_handler(CommandHandler("week", week_command))
    application.add_handler(CommandHandler("today", today_command))

    # Регистрируем обработчик текстовых сообщений
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота
    print("🤖 Бот-дневник запущен!")
    print("🔐 Добавлена система авторизации!")
    print("🗑️ Добавлена кнопка 'Удалить заметку'!")
    print("ℹ️ Добавлена кнопка 'About • Кирюша'!")
    print("⌚ Часовой пояс: Москва (МСК)")
    print(f"🔑 Пароль: {PASSWORD}")
    print(f"⏰ Таймаут неактивности: {AUTH_TIMEOUT//60} минут")
    print(f"⚠️ Максимум попыток: {AUTH_MAX_ATTEMPTS}")
    print(f"🚫 Блокировка: {AUTH_BLOCK_TIME//60} минут")

    print("\n📱 Расположение кнопок:")
    print("1. 📝 МОИ ЗАМЕТКИ (центральная, большая)")
    print("2. ⏰ Текущий урок (слева) | ➡️ Следующий урок (справа)")
    print("3. 📅 Расписание на завтра (слева) | 📖 Сегодняшние уроки (справа)")
    print("4. 📋 Вся неделя (центральная, широкая)")
    print("5. ℹ️ About • Кирюша (центральная, широкая)")

    print("\nДоступные команды:")
    print("/start - Начать")
    print("/tomorrow - Расписание на завтра")
    print("/now - Текущий урок")
    print("/next - Следующий урок")
    print("/week - Вся неделя")
    print("/today - Сегодняшние уроки")

    # Показываем текущее время МСК при запуске
    moscow_time = get_moscow_time()
    print(f"\n🕐 Текущее время МСК: {moscow_time.strftime('%H:%M:%S %d.%m.%Y')}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    while True:
        try:
            main()
        except KeyboardInterrupt:
            print("Бот остановлен.")
            break
        except Exception as e:
            print(f"Бот упал: {e}. Перезапуск через 10 сек.")
            time.sleep(10)
