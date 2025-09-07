# unified
import json
import re
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
SELECTING_CATEGORY = range(1)

# Функции для работы с данными
def load_data():
    try:
        with open('guides_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open('guides_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def build_hierarchy_path(hashtags):
    """Строит путь в иерархии из хештегов"""
    return " > ".join(hashtags)

# Обработчик сообщений из канала (админская часть)
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return

    if str(update.channel_post.chat.id) != str(config.CHANNEL_ID):
        return

    # Обработка фото с хештегами
    if update.channel_post.photo:
        caption = update.channel_post.caption or ""
        hashtags = re.findall(r'#(\w+)', caption)

        if len(hashtags) < 1:
            await update.channel_post.reply_text("Нужен хотя бы один хештег: #Категория")
            return

        file_id = update.channel_post.photo[-1].file_id
        data = load_data()

        # Строим путь в иерархии
        current_level = data
        for i, hashtag in enumerate(hashtags):
            if hashtag not in current_level:
                # Если это последний хештег - создаем запись с фото
                if i == len(hashtags) - 1:
                    current_level[hashtag] = {"photos": [file_id]}
                else:
                    current_level[hashtag] = {}
            elif i == len(hashtags) - 1:
                # Если это последний хештег и запись уже существует
                if "photos" not in current_level[hashtag]:
                    current_level[hashtag]["photos"] = []
                current_level[hashtag]["photos"].append(file_id)
            
            current_level = current_level[hashtag]

        save_data(data)

        # Формируем ответное сообщение
        hierarchy_path = build_hierarchy_path(hashtags)
        response_text = (
            f"✅ Фото добавлено!\n"
            f"📍 Путь: {hierarchy_path}\n"
            f"📸 Всего фото: {len(current_level['photos']) if 'photos' in current_level else 0}"
        )
        
        await update.channel_post.reply_text(response_text)

# Обработчик текстовых сообщений из канала (рассылка)
async def handle_channel_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post or not update.channel_post.text:
        return
    
    if str(update.channel_post.chat.id) != str(config.CHANNEL_ID):
        return
    
    message_text = update.channel_post.text
    caption = update.channel_post.caption or ""
    text_with_caption = f"{message_text}\n\n{caption}" if caption else message_text
    
    # Проверяем есть ли хештег #отправьсейчас
    if "#отправьсейчас" in text_with_caption.lower():
        # Убираем хештег из сообщения для пользователей
        clean_message = re.sub(r'#отправьсейчас', '', text_with_caption, flags=re.IGNORECASE).strip()
        
        try:
            with open('user_data.json', 'r', encoding='utf-8') as f:
                user_data = json.load(f)
        except FileNotFoundError:
            await update.channel_post.reply_text("❌ Файл user_data.json не найден")
            return
        
        users = user_data.get('users', [])
        if not users:
            await update.channel_post.reply_text("❌ Нет пользователей для рассылки")
            return
        
        success_count = 0
        fail_count = 0
        
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=clean_message
                )
                success_count += 1
                await asyncio.sleep(0.1)  # Небольшая задержка
            except Exception as e:
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
                fail_count += 1
                continue
        
        # Отправляем отчет в канал
        report_text = (
            f"📢 Мгновенная рассылка завершена!\n"
            f"✅ Успешно: {success_count}\n"
            f"❌ Не удалось: {fail_count}\n"
            f"👥 Всего пользователей: {len(users)}"
        )
        
        await update.channel_post.reply_text(report_text)
        
    else:
        # Обычная рассылка (без мгновенной отправки)
        try:
            with open('user_data.json', 'r', encoding='utf-8') as f:
                user_data = json.load(f)
        except FileNotFoundError:
            return
        
        for user_id in user_data.get('users', []):
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text
                )
                await asyncio.sleep(0.1)
            except:
                continue

# Функция для создания клавиатуры с кнопками в 2 колонки
def create_two_column_keyboard(items):
    if not items:
        return []
        
    keyboard = []
    row = []
    
    for i, item in enumerate(items):
        row.append(KeyboardButton(item))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    return keyboard

def get_current_level_data(data, current_path):
    """Получает данные для текущего уровня иерархии"""
    current_level = data
    for part in current_path:
        if part in current_level:
            current_level = current_level[part]
        else:
            return None
    return current_level

def get_available_choices(current_data):
    """Получает доступные варианты выбора для текущего уровня"""
    choices = []
    
    # Добавляем только подкатегории (ключи, которые не являются 'photos')
    for key in current_data.keys():
        if key != 'photos':
            choices.append(f"📁 {key}")
    
    return choices

async def show_photos_if_exist(update, current_data, current_path):
    """Показывает фото, если они есть в текущей категории"""
    if 'photos' in current_data and current_data['photos']:
        for i, file_id in enumerate(current_data['photos'], 1):
            await update.message.reply_photo(
                photo=file_id,
                caption=f"📸 Фото {i}/{len(current_data['photos'])}\n"
                       f"📍 {build_hierarchy_path(current_path) if current_path else 'Главное меню'}"
            )
        return True
    return False

# Обработчики для пользователей
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        return
    
    # Добавляем пользователя в базу
    try:
        with open('user_data.json', 'r', encoding='utf-8') as f:
            user_data = json.load(f)
    except FileNotFoundError:
        user_data = {"users": []}
    
    user_id = str(update.effective_user.id)
    if user_id not in user_data["users"]:
        user_data["users"].append(user_id)
        with open('user_data.json', 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
    
    data = load_data()
    
    if not data:
        await update.message.reply_text('📭 Пока нет гайдов!', reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    # Инициализируем путь пользователя
    context.user_data['current_path'] = []
    current_path = []
    
    # Показываем фото из корневой категории, если они есть
    await show_photos_if_exist(update, data, current_path)
    
    choices = get_available_choices(data)
    
    if not choices:
        await update.message.reply_text('📭 Пока нет гайдов!')
        return ConversationHandler.END
    
    # Добавляем навигационные кнопки только если есть куда возвращаться
    if current_path:
        choices.append("← Назад")
    choices.append("🏠 Главное меню")
    
    keyboard = create_two_column_keyboard(choices)
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        '🎮 Главное меню. Выбери категорию:',
        reply_markup=reply_markup
    )
    return SELECTING_CATEGORY

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        return SELECTING_CATEGORY
    
    user_choice = update.message.text
    data = load_data()
    current_path = context.user_data.get('current_path', [])
    
    # Обработка специальных команд
    if user_choice == "← Назад":
        if current_path:
            current_path.pop()
            context.user_data['current_path'] = current_path
    
    elif user_choice == "🏠 Главное меню":
        context.user_data['current_path'] = []
        current_path = []
    
    elif user_choice.startswith("📁 "):
        # Переход в подкатегорию
        category_name = user_choice[2:]  # Убираем эмодзи
        current_path.append(category_name)
        context.user_data['current_path'] = current_path
    
    else:
        await update.message.reply_text("❌ Неизвестная команда")
        return SELECTING_CATEGORY
    
    # Получаем данные для нового уровня
    if current_path:
        parent_path = current_path[:-1]
        parent_data = get_current_level_data(data, parent_path) if parent_path else data
        current_data = get_current_level_data(data, current_path)
    else:
        parent_data = data
        current_data = data
    
    if current_data is None:
        await update.message.reply_text("❌ Категория не найдена")
        # Возвращаемся на уровень выше
        if current_path:
            current_path.pop()
            context.user_data['current_path'] = current_path
            current_data = get_current_level_data(data, current_path) if current_path else data
        else:
            current_data = data
    
    # Автоматически показываем фото, если они есть в этой категории
    has_photos = await show_photos_if_exist(update, current_data, current_path)
    
    # ВАЖНОЕ ИЗМЕНЕНИЕ: После показа фото возвращаемся на уровень ВЫШЕ
    # чтобы можно было выбирать другие категории на том же уровне
    if has_photos and current_path:
        # После показа фото возвращаемся к родительскому уровню
        parent_path = current_path[:-1]
        context.user_data['current_path'] = parent_path
        current_path = parent_path
        current_data = get_current_level_data(data, parent_path) if parent_path else data
    
    choices = get_available_choices(current_data)
    
    if not choices and not has_photos:
        await update.message.reply_text("📭 В этой категории пока ничего нет")
        if current_path:
            current_path.pop()
            context.user_data['current_path'] = current_path
            current_data = get_current_level_data(data, current_path) if current_path else data
            choices = get_available_choices(current_data)
        else:
            choices = get_available_choices(data)
    
    # Добавляем навигационные кнопки
    if current_path:
        choices.append("← Назад")
    choices.append("🏠 Главное меню")
    
    keyboard = create_two_column_keyboard(choices)
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if current_path:
        await update.message.reply_text(
            f"📍 Текущий путь: {build_hierarchy_path(current_path)}\n"
            f"Выбери категорию:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            '🎮 Главное меню. Выбери категорию:',
            reply_markup=reply_markup
        )
    
    return SELECTING_CATEGORY

def main():
    application = Application.builder().token(config.ADMIN_BOT_TOKEN).build()
    
    # Обработчик для фото из канала
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.PHOTO, 
        handle_channel_post
    ))

    # Обработчик для текста из канала (включая #отправьсейчас)
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.TEXT,
        handle_channel_text
    ))
    
    # Обработчики для пользователей
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_CATEGORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_selection)
            ],
        },
        fallbacks=[],
    )
    
    application.add_handler(conv_handler)
    
    print("Бот запущен! Слушает канал и отвечает пользователям!")
    application.run_polling()

if __name__ == '__main__':

    main()
