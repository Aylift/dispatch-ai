Features:
- Redis i/lub celery w tło wrzucić przetwarzanie audio z Deepgram
- dates for task, calendar widget or smth
- descriptions of tasks
- separate tab for planning stuff in tasks
- subtasks, complete parent when done
- recurring tasks
- notifications, reminders
- Smart deduplication / caching (Redis) — As tasks grow, the LLM re-parsing or re-transcribing the same input wastes money and time. Redis can cache "this exact voice snippet already resolved to these tasks" so it's instant and costs $0 the second time.
- when selecting new prio for an item highlight it with some color, to make it stand out and not miss it when it moves
- separate tab for "TODAY" tasks, that can be moved here from main list, they stay on main list though with tag "TODAY"
- timebox
BUGS:
-
