import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
import services
from handlers import start, tasks, checklists, punishments, justice, reminders, \
    materials, stats, admin


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    services.set_bot(bot)

    for r in (start.router, tasks.router, checklists.router, punishments.router,
              justice.router, reminders.router, materials.router, stats.router,
              admin.router):
        dp.include_router(r)

    scheduler = AsyncIOScheduler()
    services.scheduler_jobs(scheduler)
    from handlers.justice import appeal_deadline_tick
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler.add_job(appeal_deadline_tick, IntervalTrigger(minutes=2), id="appeals")
    scheduler.start()

    me = await bot.get_me()
    logging.info("Бот запущен: @%s", me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
