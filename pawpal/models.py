"""Core data model and scheduling logic for PawPal+."""
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class Task:
    """Represents a single activity for a pet."""
    _id_counter = 1

    def __init__(
        self,
        description: str,
        time: Optional[datetime] = None,
        frequency: str = '',
        completed: bool = False,
        duration: int = 0,
        priority: str = 'medium',
    ):
        self.task_id = Task._id_counter
        Task._id_counter += 1
        self.description = description
        self.time = time
        self.frequency = frequency
        self.completed = completed
        self.duration = duration
        self.priority = priority

    def mark_complete(self):
        """Mark this task as complete."""
        self.completed = True

    def mark_incomplete(self):
        """Mark this task as incomplete."""
        self.completed = False


class Pet:
    """Stores pet details and a list of tasks."""
    _id_counter = 1

    def __init__(self, name: str, species: str, breed: str = '', age: int = 0):
        self.pet_id = Pet._id_counter
        Pet._id_counter += 1
        self.name = name
        self.species = species
        self.breed = breed
        self.age = age
        self.tasks: List[Task] = []

    def add_task(self, task: Task) -> None:
        """Add a task to this pet's task list."""
        self.tasks.append(task)

    def get_tasks(self) -> List[Task]:
        """Return all tasks for this pet."""
        return self.tasks


class Owner:
    """Manages multiple pets and provides access to all their tasks."""

    def __init__(self, name: str, preferences: Optional[Dict] = None):
        self.name = name
        self.pets: List[Pet] = []
        self.preferences: Dict = preferences if preferences is not None else {
            'max_tasks_per_day': 5,
            'available_minutes': 90,
        }

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner."""
        self.pets.append(pet)

    def set_preferences(self, prefs: Dict) -> None:
        """Update owner preferences with the given key-value pairs."""
        self.preferences.update(prefs)

    def get_all_tasks(self) -> List[Task]:
        """Return all tasks for all pets owned by this owner."""
        return [task for pet in self.pets for task in pet.get_tasks()]


class Scheduler:
    """The 'Brain' that retrieves, organizes, and manages tasks across pets."""

    def __init__(self, owner: Owner):
        """Initialize the Scheduler with an Owner."""
        self.owner = owner

    def get_all_tasks(self) -> List[Task]:
        """Retrieve all tasks from all pets."""
        return self.owner.get_all_tasks()

    def get_tasks_by_pet(self, pet: Pet) -> List[Task]:
        """Retrieve all tasks for a specific pet."""
        return pet.get_tasks()

    def get_tasks_by_status(self, completed: bool) -> List[Task]:
        """Retrieve tasks filtered by completion status."""
        return [task for task in self.get_all_tasks() if task.completed == completed]

    def filter_by_pet_name(self, pet_name: str) -> List[Task]:
        """Return all tasks belonging to the pet with the given name (case-insensitive)."""
        matched_pet = next(
            (p for p in self.owner.pets if p.name.lower() == pet_name.lower()), None
        )
        if matched_pet is None:
            return []
        return matched_pet.get_tasks()

    def filter_tasks(
        self, completed: Optional[bool] = None, pet_name: Optional[str] = None
    ) -> List[Task]:
        """Filter tasks by completion status, pet name, or both combined."""
        tasks = self.get_all_tasks()
        if pet_name is not None:
            tasks = [
                task for task in tasks
                if any(
                    task in p.tasks
                    for p in self.owner.pets
                    if p.name.lower() == pet_name.lower()
                )
            ]
        if completed is not None:
            tasks = [task for task in tasks if task.completed == completed]
        return tasks

    def get_tasks_by_frequency(self, frequency: str) -> List[Task]:
        """Retrieve tasks filtered by frequency."""
        return [task for task in self.get_all_tasks() if task.frequency == frequency]

    def complete_task(self, pet: Pet, task: Task) -> None:
        """Mark a task complete and auto-schedule the next occurrence if recurring.

        Daily tasks get a +1 day follow-up; weekly tasks get +7 days.
        'once' and 'monthly' tasks are terminal — no follow-up is created.
        Tasks with no scheduled time are marked done without rescheduling.
        """
        task.mark_complete()

        _delta_map = {
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
        }
        delta = _delta_map.get(task.frequency)

        if delta and task.time:
            next_task = Task(
                description=task.description,
                time=task.time + delta,
                frequency=task.frequency,
                duration=task.duration,
                priority=task.priority,
            )
            pet.add_task(next_task)

    def sort_by_time(self) -> List[Task]:
        """Return all tasks sorted by scheduled time ascending; timeless tasks go last."""
        return sorted(
            self.get_all_tasks(),
            key=lambda task: task.time if task.time is not None else datetime.max
        )

    def detect_conflicts(self) -> List[str]:
        """Detect tasks sharing an identical datetime within the same pet's schedule."""
        warnings: List[str] = []
        for pet in self.owner.pets:
            timed_tasks = [t for t in pet.get_tasks() if t.time is not None]
            for i in range(len(timed_tasks)):
                for j in range(i + 1, len(timed_tasks)):
                    if timed_tasks[i].time == timed_tasks[j].time:
                        time_str = timed_tasks[i].time.strftime('%H:%M')
                        warnings.append(
                            f"WARNING: '{timed_tasks[i].description}' and "
                            f"'{timed_tasks[j].description}' are both scheduled at "
                            f"{time_str} for {pet.name}."
                        )
        return warnings

    def generate_schedule(self) -> List[tuple]:
        """Select and order tasks for today based on priority and owner constraints.

        Returns a list of (pet, task, reason) tuples capped by max_tasks_per_day
        and available_minutes preferences. High priority tasks are selected first.
        """
        _priority_rank = {'high': 0, 'medium': 1, 'low': 2}
        max_tasks = self.owner.preferences.get('max_tasks_per_day', 5)
        available_minutes = self.owner.preferences.get('available_minutes', 90)

        candidates = [
            (pet, task)
            for pet in self.owner.pets
            for task in pet.get_tasks()
            if not task.completed
        ]
        candidates.sort(
            key=lambda pt: (
                _priority_rank.get(pt[1].priority, 1),
                pt[1].time if pt[1].time else datetime.max,
            )
        )

        selected = []
        minutes_used = 0
        for pet, task in candidates:
            if len(selected) >= max_tasks:
                break
            if task.duration > 0 and minutes_used + task.duration > available_minutes:
                continue
            minutes_used += task.duration
            time_str = task.time.strftime('%H:%M') if task.time else 'anytime'
            mins_remaining = available_minutes - minutes_used
            reason = (
                f"Selected – {task.priority} priority · "
                f"{task.duration} min · {mins_remaining} min remaining after"
                if task.duration > 0
                else f"Selected – {task.priority} priority · scheduled {time_str}"
            )
            selected.append((pet, task, reason))

        return selected

    def explain_plan(self) -> str:
        """Return a plain-text summary of the generated schedule with per-task reasoning."""
        schedule = self.generate_schedule()
        if not schedule:
            return "No tasks selected for today. Add tasks or adjust preferences."
        lines = ["Today's plan:\n"]
        for i, (pet, task, reason) in enumerate(schedule, 1):
            time_str = task.time.strftime('%H:%M') if task.time else 'no time set'
            lines.append(f"  {i}. [{pet.name}] {task.description} @ {time_str} — {reason}")
        return "\n".join(lines)
