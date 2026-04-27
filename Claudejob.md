---

## Smarter Scheduling

Phase 2 adds intelligent scheduling algorithms to the `Scheduler` class, making PawPal+ more useful and reliable for pet owners.

### Sorting

`sort_by_time()` returns all tasks across every pet ordered by scheduled time, earliest first. Tasks without a time are pushed to the end. Uses Python's `sorted()` with a `lambda` key on `task.time`, falling back to `datetime.max` for timeless tasks.

### Filtering

Two methods allow owners to quickly find the tasks they care about:

- `filter_by_pet_name(pet_name)` — returns all tasks for a specific pet by name (case-insensitive).
- `filter_tasks(completed, pet_name)` — a flexible combined filter; pass either or both arguments to narrow results by completion status, pet, or both at once.

### Recurring Tasks

`complete_task(pet, task)` marks a task done and automatically schedules the next occurrence for `daily` (+1 day) and `weekly` (+7 days) tasks using Python's `timedelta`. One-time (`once`) and `monthly` tasks are marked complete without generating a follow-up. This keeps the `Scheduler` as the "Brain" — `Task` and `Pet` stay simple.

### Conflict Detection

`detect_conflicts()` scans each pet's task list for tasks booked at the exact same time and returns plain-text warning messages. Conflicts are only flagged within the same pet's schedule. Returns an empty list when no conflicts exist — safe to iterate without any extra checks.

## Testing PawPal+

1. python -m pytest. Confidence Level ⭐️ ⭐️ ⭐️ ⭐️

The test cover
Creates a bare Task and verifies it starts as incomplete (completed=False). Calls mark_complete() and confirms the flag flips to True. Tests the most basic state change on a Task.

`test_task_addition_to_pet()`
Creates a Pet with no tasks, records the initial count, adds one Task, and asserts the count increased by exactly 1. Confirms add_task() actually appends to the pet's task list.

`test_sort_by_time_chronological_order()`
Adds four tasks to a pet out of order (evening first, then timeless, then morning, then afternoon). Calls sort_by_time() and asserts the returned list is in ascending time order — morning → afternoon → evening — and that the task with time=None lands at the very end.

`test_complete_daily_task_creates_next_occurrence()`
Creates a daily task with a specific datetime and calls complete_task(). Verifies three things: the original task is marked done, a second task was automatically created, and that new task has the same description/frequency but is scheduled exactly +1 day later and starts as incomplete.

`test_detect_conflicts_flags_duplicate_times()`
Gives a pet two tasks at the same time (10:00) and one at a different time (11:00). Calls detect_conflicts() and asserts exactly one warning is returned, and that warning message mentions both conflicting task names, the time "10:00", and the pet's name "Rex".

`test_detect_conflicts_no_false_positives()`
Gives a pet two tasks at different times and confirms detect_conflicts() returns an empty list — ensuring the method doesn't generate false alarms when there are no real conflicts.

## Demo


<a href="pawpal_screenshot.png" target="_blank"><img src='pawpal_screenshot.png'/>


![alt text](pawpal_screenshot.png)
