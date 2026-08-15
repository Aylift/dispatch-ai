Features:
- Redis i/lub celery w tło wrzucić przetwarzanie audio z Deepgram
- dates for task, calendar widget or smth
- descriptions of tasks
- separate tab for planning stuff in tasks
- subtasks, complete parent when done
- recurring tasks
- notifications, reminders
- Smart deduplication / caching (Redis) — As tasks grow, the LLM re-parsing or re-transcribing the same input wastes money and time. Redis can cache "this exact voice snippet already resolved to these tasks" so it's instant and costs $0 the second time.
- sort by created_at or priority, when changing priority and task would move, I need some subtle animation that task is flowing up or down, and other tasks are going down or up as well, rn it's just instant and looks soo bad, is bad for ux. While we're at it, priority selector now sits on the right and user wouldn't have a clue what it do without testing for some time, so we need to make it clear what it does.
- when selecting new prio for an item highlight it with some color, to make it stand out and not miss it when it moves
- db backups and hide it somewhere on the system
- separate tab for "TODAY" tasks, that can be moved here from main list, they stay on main list though with tag "TODAY"
BUGS:
- voice is glitchy, maybe choose microphone button cause not sure whether it's mic problem, not transcritpion, if that won't work we'll fix transcription
