"""Demonstration of all Scheduler features. Run from project root: python scripts/demo.py"""
from datetime import datetime
from pawpal.models import Owner, Pet, Task, Scheduler

owner = Owner(name="Alex")

pet1 = Pet(name="Buddy", species="Dog", breed="Labrador", age=5)
pet2 = Pet(name="Mittens", species="Cat", breed="Siamese", age=3)
owner.add_pet(pet1)
owner.add_pet(pet2)

now = datetime.now()
task3 = Task(description="Playtime",            time=now.replace(hour=17, minute=0), frequency="daily")
task6 = Task(description="Evening cuddle",      time=now.replace(hour=17, minute=0), frequency="weekly")
task1 = Task(description="Morning walk",        time=now.replace(hour=7,  minute=0), frequency="daily")
task5 = Task(description="Feed dinner",         time=now.replace(hour=18, minute=0), frequency="daily")
task4 = Task(description="Litter box cleaning", time=now.replace(hour=9,  minute=0), frequency="daily")
task2 = Task(description="Feed breakfast",      time=now.replace(hour=8,  minute=0), frequency="daily")

pet1.add_task(task3)
pet1.add_task(task1)
pet1.add_task(task2)
pet2.add_task(task6)
pet2.add_task(task4)
pet2.add_task(task5)

task1.mark_complete()

scheduler = Scheduler(owner)

print("=== Sorted Schedule (sort_by_time) ===")
for task in scheduler.sort_by_time():
    pet_name = next((p.name for p in owner.pets if task in p.tasks), "Unknown")
    time_str = task.time.strftime('%H:%M') if task.time else 'No time'
    print(f"  {time_str} | {task.description:<25} | Pet: {pet_name}")

print("\n=== Pending Tasks ===")
for task in scheduler.filter_tasks(completed=False):
    print(f"  [ ] {task.description}")

print("\n=== Completed Tasks ===")
for task in scheduler.filter_tasks(completed=True):
    print(f"  [x] {task.description}")

print("\n=== Buddy's Tasks Only ===")
for task in scheduler.filter_by_pet_name("Buddy"):
    time_str = task.time.strftime('%H:%M') if task.time else 'No time'
    print(f"  {time_str} | {task.description}")

print("\n=== Mittens' Pending Tasks ===")
for task in scheduler.filter_tasks(completed=False, pet_name="Mittens"):
    time_str = task.time.strftime('%H:%M') if task.time else 'No time'
    print(f"  {time_str} | {task.description}")

print("\n=== Recurring Task Demo (complete_task) ===")
print("  Buddy's tasks BEFORE:")
for task in scheduler.filter_by_pet_name("Buddy"):
    time_str = task.time.strftime('%H:%M') if task.time else 'No time'
    status = "done" if task.completed else "pending"
    print(f"    {time_str} | {task.description} [{status}]")

scheduler.complete_task(pet1, task1)

print("  Buddy's tasks AFTER:")
for task in scheduler.filter_by_pet_name("Buddy"):
    time_str = task.time.strftime('%Y-%m-%d %H:%M') if task.time else 'No time'
    status = "done" if task.completed else "pending"
    print(f"    {time_str} | {task.description} [{status}]")

print("\n=== Conflict Detection Demo ===")
conflict_task = Task(description="Vet check-in", time=now.replace(hour=17, minute=0), frequency="once")
pet1.add_task(conflict_task)

warnings = scheduler.detect_conflicts()
if warnings:
    for msg in warnings:
        print(f"  {msg}")
else:
    print("  No conflicts detected.")
