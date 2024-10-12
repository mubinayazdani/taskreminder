from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import datetime
import logging
import pytz
import asyncio

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = 'TOKEN'

reminders = {}
scheduled_tasks = {}
birthday_reminders = {}

TIMEZONE = pytz.timezone('Asia/Tehran')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🆔 چت آیدی", callback_data='get_id'),
         InlineKeyboardButton("⏰ ریمایندر", callback_data='set_reminder')],
        [InlineKeyboardButton("👀 ریمایندرها", callback_data='view_reminders'),
         InlineKeyboardButton("🎂 تولد", callback_data='set_birthday')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🎉 خوش آمدید! گزینه‌ای انتخاب کنید:', reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'get_id':
        await query.message.reply_text(f'چت آیدی شما: {query.message.chat.id}')
    elif query.data == 'set_reminder':
        await query.message.reply_text('لطفاً برای تنظیم ریمایندر، زمان مورد نظر خود را مشخص کنید، مانند: 16:23')
        context.user_data['awaiting_time'] = True
    elif query.data == 'view_reminders':
        await view_reminders(update, context)
    elif query.data.startswith('edit_'):
        reminder_id = query.data.split('_')[1]
        context.user_data['editing_remind_id'] = reminder_id
        await edit_reminder(update, context)
    elif query.data.startswith('delete_'):
        reminder_id = query.data.split('_')[1]
        await delete_reminder(update, context, reminder_id)
    elif query.data == 'set_birthday':
        await query.message.reply_text('لطفا تاریخ تولد را به فرمت YYYY-MM-DD وارد کنید.')
        context.user_data['awaiting_birthday'] = True  # Set state to await birthday


async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    user_reminders = reminders.get(chat_id, {})

    if not user_reminders:
        await query.message.reply_text('شما ریمایندری تنظیم نکرده‌اید.')
        return

    keyboard = []
    for reminder_id, (reminder_time, task_id, task_type, recurrence_type) in user_reminders.items():
        time_str = reminder_time.strftime("%H:%M")
        recurrence_display = recurrence_type if recurrence_type else "هیچکدام"

        # Use descriptive text for each reminder
        button_edit = InlineKeyboardButton("🖋️ ادیت", callback_data=f'edit_{reminder_id}')
        button_delete = InlineKeyboardButton("❌ حذف", callback_data=f'delete_{reminder_id}')

        keyboard.append(
            [InlineKeyboardButton(f'ریمایندر: {task_id} - {time_str} ({recurrence_display})', callback_data='dummy')])
        keyboard.append([button_edit, button_delete])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text('🔔 ریمایندرهای شما:', reply_markup=reply_markup)


async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE, reminder_id: str) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id

    if chat_id in reminders and reminder_id in reminders[chat_id]:
        del reminders[chat_id][reminder_id]  # Remove reminder from storage

        if reminder_id in scheduled_tasks:
            scheduled_tasks[reminder_id].cancel()
            del scheduled_tasks[reminder_id]
        await query.message.reply_text('ریمایندر با موفقیت حذف شد.')
    else:
        await query.message.reply_text('ریمایندر یافت نشد.')


async def edit_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reminder_id = context.user_data['editing_remind_id']
    chat_id = update.callback_query.from_user.id
    user_reminders = reminders.get(chat_id, {})

    if reminder_id in user_reminders:
        reminder_time, task_id, task_type, recurrence_type = user_reminders[reminder_id]
        context.user_data['awaiting_time_edit'] = True
        await update.callback_query.message.reply_text(
            f'زمان ریمایندر: {reminder_time.strftime("%H:%M")}.لطفا زمان جدید را ارسال کنید:'
        )
    else:
        await update.callback_query.message.reply_text("ریمایندری یافت نشد.")


async def schedule_birthday_reminders():
    while True:
        now = datetime.datetime.now(TIMEZONE)
        today = now.date()

        for chat_id, birthday_date in birthday_reminders.items():
            # Check if today is the birthday
            if birthday_date.month == today.month and birthday_date.day == today.day:
                await remind_user(app.bot, chat_id, f"امروز روز تولد، یادت نره تبریک بگی! 🎉", 'text')

        await asyncio.sleep(86400)  # Check daily


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat.id

    if context.user_data.get('awaiting_time_edit'):
        time_str = update.message.text
        try:
            reminder_time = datetime.datetime.strptime(time_str, '%H:%M').time()
            context.user_data['reminder_time'] = reminder_time
            if 'editing_remind_id' in context.user_data:
                reminder_id = context.user_data['editing_remind_id']
                now = datetime.datetime.now(TIMEZONE)
                if reminder_time < now.time():
                    reminder_time = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), reminder_time)
                else:
                    reminder_time = datetime.datetime.combine(now.date(), reminder_time)

                reminder_time = TIMEZONE.localize(reminder_time)
                current_task_id, task_type, recurrence_type = reminders[chat_id][reminder_id][1:4]

                reminders[chat_id][reminder_id] = (reminder_time, current_task_id, task_type, recurrence_type)

                await update.message.reply_text(
                    'لطفا تسک مورد علاقه خودتون رو ارسال کنید؛ (به صورت ویس هم میتونید ارسال کنید.)')
                context.user_data['awaiting_task_edit'] = True
                del context.user_data['awaiting_time_edit']
            else:
                await update.message.reply_text("چت آیدی مورد نظر یافت نشد.")

        except ValueError:
            await update.message.reply_text('لطفا زمان را در قالب صحیح ارسال کنید.')

    # Check if we are expecting a new task input for editing
    elif context.user_data.get('awaiting_task_edit'):
        reminder_time = context.user_data.get('reminder_time')
        if update.message.voice:
            task_id = update.message.voice.file_id
            task_type = 'voice'
        elif update.message.text:
            task_id = update.message.text
            task_type = 'text'
        else:
            await update.message.reply_text('لطفا تسک مد نظر خودتون رو در قالب متن و یا ویس ارسال کنید.')
            return

        reminder_id = context.user_data['editing_remind_id']
        # Update the task for the reminder
        reminder_time, _, _, recurrence_type = reminders[chat_id][reminder_id]
        reminders[chat_id][reminder_id] = (
        reminder_time, task_id, task_type, recurrence_type)

        if reminder_id in scheduled_tasks:
            scheduled_tasks[reminder_id].cancel()  # Cancel the old schedule
            del scheduled_tasks[reminder_id]  # Clean up entry from scheduled tasks

        # Updated code for reminder time check
        now = datetime.datetime.now(TIMEZONE)  # Use the relevant timezone
        if reminder_time.time() < now.time():  # Compare only the time part for correct checking
            reminder_time = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), reminder_time.time())
        else:
            reminder_time = datetime.datetime.combine(now.date(), reminder_time.time())

        reminder_time = TIMEZONE.localize(reminder_time)
        task = asyncio.create_task(
            schedule_reminder(chat_id, task_id, task_type, reminder_time, recurrence_type, reminder_id))
        scheduled_tasks[reminder_id] = task

        await update.message.reply_text("ریمایندر با موفقیت به روز رسانی شد.")
        del context.user_data['awaiting_task_edit']
        del context.user_data['editing_remind_id']
    elif context.user_data.get('awaiting_time'):
        time_str = update.message.text
        try:
            reminder_time = datetime.datetime.strptime(time_str, '%H:%M').time()
            context.user_data['reminder_time'] = reminder_time
            await update.message.reply_text('ریمایندر چگونه یادآوری بشه؟ (روزانه,هفتگی, ماهانه, هیچکدام.)')
            context.user_data['awaiting_time'] = False
            context.user_data['awaiting_recurrence'] = True
        except ValueError:
            await update.message.reply_text('زمان را در قالب صحیح ارسال کنید.')

    # Handle other message logic
    elif context.user_data.get('awaiting_recurrence'):
        recurrence_type = update.message.text.lower()
        if recurrence_type not in ['روزانه', 'هفتگی', 'ماهانه', 'هیچکدام']:
            await update.message.reply_text('ریمایندر چگونه یادآوری بشود؟ (روزانه,هفتگی, ماهانه, هیچکدام.)')
            return
        context.user_data['recurrence_type'] = recurrence_type
        await update.message.reply_text(
            ' تسک مدنظر خود را ارسال کنید (در قالب ویس و یا متن):')
        context.user_data['awaiting_recurrence'] = False
        context.user_data['awaiting_task'] = True

    elif context.user_data.get('awaiting_birthday'):
        try:
            birthday_str = update.message.text
            birthday_date = datetime.datetime.strptime(birthday_str, '%Y-%m-%d').date()
            birthday_reminders[chat_id] = birthday_date  # Store the birthday
            await update.message.reply_text(f'تبریک! تاریخ تولد شما به عنوان {birthday_date} ثبت شد.')
            context.user_data['awaiting_birthday'] = False
        except ValueError:
            await update.message.reply_text('لطفا تاریخ را به فرمت صحیح وارد کنید: YYYY-MM-DD')

    elif context.user_data.get('awaiting_task'):
        reminder_time = context.user_data.get('reminder_time')
        recurrence_type = context.user_data.get('recurrence_type')

        if update.message.voice:
            task_id = update.message.voice.file_id
            task_type = 'voice'
        elif update.message.text:
            task_id = update.message.text
            task_type = 'text'
        else:
            await update.message.reply_text('Please send a valid task in either text or voice format.')
            return

        now = datetime.datetime.now(TIMEZONE)  # Use the relevant timezone

        # Calculate the correct reminder_time
        if reminder_time < now.time():
            reminder_time = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), reminder_time)
        else:
            reminder_time = datetime.datetime.combine(now.date(), reminder_time)

        reminder_time = TIMEZONE.localize(reminder_time)

        reminder_id = str(len(reminders.get(chat_id, {})) + 1)
        if chat_id not in reminders:
            reminders[chat_id] = {}

        reminders[chat_id][reminder_id] = (reminder_time, task_id, task_type, recurrence_type)

        task = asyncio.create_task(
            schedule_reminder(chat_id, task_id, task_type, reminder_time, recurrence_type, reminder_id))
        scheduled_tasks[reminder_id] = task  # Store the task with reminder_id
        await update.message.reply_text(
            f'  ریمایندر ثبت شد با {reminder_time.strftime("%H:%M")} تکرار {recurrence_type} .')


async def schedule_reminder(chat_id: int, task_id: str, task_type: str, reminder_time: datetime.datetime,
                            recurrence_type: str, reminder_id: str):
    try:
        while True:
            now = datetime.datetime.now(TIMEZONE)
            wait_time = (reminder_time - now).total_seconds()

            if wait_time <= 0:
                await remind_user(app.bot, chat_id, task_id, task_type)

                if recurrence_type == 'روزانه':
                    reminder_time += datetime.timedelta(days=1)
                elif recurrence_type == 'هفتگی':
                    reminder_time += datetime.timedelta(weeks=1)
                elif recurrence_type == 'ماهانه':
                    next_month = reminder_time.month + 1
                    if next_month > 12:
                        next_month = 1
                        reminder_time = reminder_time.replace(year=reminder_time.year + 1)
                    reminder_time = reminder_time.replace(month=next_month)
                else:
                    break
            else:
                await asyncio.sleep(min(wait_time, 60))  # Check again after 60 seconds
    except asyncio.CancelledError:
        logger.info(f"Reminder {reminder_id} for chat {chat_id} has been canceled.")


async def remind_user(bot, chat_id, task_id, task_type):
    if task_type == 'text':
        await bot.send_message(chat_id, f"Reminder: {task_id}")
    elif task_type == 'voice':
        await bot.send_voice(chat_id, task_id)


def main() -> None:
    global app
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_message))

    # Create the birthday reminders task after starting the application
    async def schedule_tasks():
        await schedule_birthday_reminders()

    app.run_polling()

    # Create the scheduled birthday reminders task
    asyncio.run_coroutine_threadsafe(schedule_tasks(), app.loop)


if __name__ == "__main__":
    main()




