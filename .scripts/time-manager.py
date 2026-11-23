#!/usr/bin/env python3
"""
time_manager_v7.py - Emacs Org-mode Time & Telemetry Manager for Kronos (v7)

Manages time.org daily entries, template expansion, task rollovers,
scheduled timestamps for Org Agenda, food/workout log integration, and daily stat calculations.

Updates in v7:
- Removed --bmr CLI argument parameter.
- BMR is extracted directly from the workout log JSON (athlete.bmr_kcal).
- Daily calorie balance: Food Intake - (Active Workout Burn + BMR from workout log).

Usage:
  # Start a new day
  python3 time_manager_v7.py --day-start [--date YYYY-MM-DD] [--file path/to/time.org]

  # End a day
  python3 time_manager_v7.py --day-end [--date YYYY-MM-DD] [--file path/to/time.org]
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime

DEFAULT_ORG_HEADER = "#+TODO: TODO | DONEFORTODAY DONE FAILED\n"
DEFAULT_FILE_PATH = "../self-sustainer/self-manager/time/time.org"
DEFAULT_FALLBACK_BMR_KCAL = 1950.0


def parse_args():
    parser = argparse.ArgumentParser(description="Kronos time.org Manager Script v7")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--day-start", action="store_true", help="Initialize a new day entry in time.org")
    mode_group.add_argument("--day-end", action="store_true", help="Finalize a day entry, calculate stats & balance")

    parser.add_argument("--date", type=str, help="Target date in YYYY-MM-DD format (defaults to today)")
    parser.add_argument("--file", type=str, default=DEFAULT_FILE_PATH, help=f"Path to time.org file (default: {DEFAULT_FILE_PATH})")
    parser.add_argument("--schedules-dir", type=str, default="schedules", help="Path to schedules directory")
    parser.add_argument("--logs-dir", type=str, default="logs", help="Path to logs directory")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing day on day-start")

    # Telemetry CLI inputs for non-interactive mode
    parser.add_argument("--kg", type=float, help="Body weight measurement in Kg")
    parser.add_argument("--tobacco", type=int, help="Tobacco units consumed")
    parser.add_argument("--km-driven", type=float, help="Kilometers driven")
    parser.add_argument("--steps", type=int, help="Daily step count")
    parser.add_argument("--sleep-hrs", type=float, help="Hours slept")

    return parser.parse_args()


def get_date_info(date_str=None):
    if date_str:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        dt = datetime.now()
    year_str = dt.strftime("%Y")
    month_name = dt.strftime("%B")
    day_name = dt.strftime("%A")
    date_formatted = dt.strftime("%Y-%m-%d")
    short_day = dt.strftime("%a")
    day_header_str = f"*** <{date_formatted} {short_day}>"
    return dt, year_str, month_name, day_name, date_formatted, short_day, day_header_str


def ensure_org_header(content):
    if "#+TODO:" not in content:
        return DEFAULT_ORG_HEADER + "\n" + content
    else:
        def replace_todo_line(match):
            return "#+TODO: TODO | DONEFORTODAY DONE FAILED"
        return re.sub(r"#\+TODO:.*", replace_todo_line, content)


def load_json_file(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def find_previous_day_rollovers(content, current_date_str):
    """
    Finds the last recorded day before current_date_str in content,
    and extracts tasks in 'ToDos for the day' marked DONEFORTODAY or FAILED.
    """
    day_blocks = list(re.finditer(r"^\*\*\* <(\d{4}-\d{2}-\d{2}) [^>]+>", content, re.MULTILINE))
    if not day_blocks:
        return []

    prev_block_content = None
    for i in range(len(day_blocks) - 1, -1, -1):
        match = day_blocks[i]
        b_date = match.group(1)
        if b_date < current_date_str:
            start_pos = match.start()
            end_pos = day_blocks[i+1].start() if i + 1 < len(day_blocks) else len(content)
            prev_block_content = content[start_pos:end_pos]
            break

    if not prev_block_content:
        return []

    # Extract ToDos for the day section
    todos_for_day_match = re.search(r"\*\*\*\*\*\* ToDos for the day.*?(?=\n\*\*\*\*\*\* |\n\*\*\*\*\* |\n\*\*\*\* |\Z)", prev_block_content, re.DOTALL)
    if not todos_for_day_match:
        return []

    sec_text = todos_for_day_match.group(0)
    rollover_items = []

    pattern = r"^\*+\s+(DONEFORTODAY|FAILED)\s+(.+)$"
    for line in sec_text.splitlines():
        line_clean = line.strip()
        m = re.match(pattern, line_clean)
        if m:
            task_name = m.group(2).strip()
            # Strip out SCHEDULED: lines if matched
            if not task_name.startswith("SCHEDULED:"):
                rollover_items.append(task_name)

    return rollover_items


def build_todo_entry(task_name, date_formatted, short_day, depth=7):
    stars = "*" * depth
    indent = " " * (depth + 1)
    return f"{stars} TODO {task_name}\n{indent}SCHEDULED: <{date_formatted} {short_day}>"


def build_day_start_block(date_info, daily_sched, weekly_sched, rollovers):
    dt, year_str, month_name, day_name, date_formatted, short_day, day_header_str = date_info

    lines = [day_header_str]
    lines.append("**** ToDo")

    # Routine section
    lines.append("***** Routine")
    routine_dict = daily_sched.get("Routine", {})
    for subcat, tasks in routine_dict.items():
        lines.append(f"****** {subcat}")
        for task in tasks:
            lines.append(build_todo_entry(task, date_formatted, short_day, depth=7))

    # Outside activities
    lines.append("***** Outside activities")
    outside_tasks = weekly_sched.get(day_name, [])
    if outside_tasks:
        for task in outside_tasks:
            lines.append(build_todo_entry(task, date_formatted, short_day, depth=6))

    # Current ToDos section
    lines.append("***** Current ToDos")
    lines.append("****** ToDos for the day")
    for r_task in rollovers:
        lines.append(build_todo_entry(r_task, date_formatted, short_day, depth=7))

    current_todos = daily_sched.get("Current ToDos", {})
    for subcat, tasks in current_todos.items():
        if subcat == "ToDos for the day":
            for task in tasks:
                if task not in rollovers:
                    lines.append(build_todo_entry(task, date_formatted, short_day, depth=7))
        else:
            lines.append(f"****** {subcat}")
            for task in tasks:
                lines.append(build_todo_entry(task, date_formatted, short_day, depth=7))

    # Workout section placeholder
    lines.append("**** Workout")

    # Food section placeholder
    lines.append("**** Food")

    # Stat table placeholder
    lines.append("**** Stat table")
    lines.append("     |------+---------+-----------+-------+-----------+-------------+---------+--------------|")
    lines.append("     |   Kg | Tobacco | Km driven | Steps | Sleep hrs | Workout min | Goals % | kCal balance |")
    lines.append("     |------+---------+-----------+-------+-----------+-------------+---------+--------------|")
    lines.append("     |  0.0 |       0 |         0 |     0 |         0 |           0 |       0 |            0 |")
    lines.append("     |------+---------+-----------+-------+-----------+-------------+---------+--------------|")

    return "\n".join(lines) + "\n"


def insert_day_start_into_org(content, day_block, date_info, force=False):
    dt, year_str, month_name, day_name, date_formatted, short_day, day_header_str = date_info
    content = ensure_org_header(content)

    if day_header_str in content:
        if not force:
            print(f"Warning: Entry for {date_formatted} already exists in file. Use --force to overwrite.")
            return content
        else:
            pattern = re.escape(day_header_str) + r".*?(?=\n\*\*\* <|\n\* |\Z)"
            content = re.sub(pattern, day_block.strip(), content, flags=re.DOTALL)
            return content

    year_header = f"* {year_str}"
    month_header = f"** {month_name}"

    year_pos = content.find(year_header)
    if year_pos == -1:
        new_block = f"{year_header}\n{month_header}\n{day_block}"
        return content.rstrip() + "\n\n" + new_block if content.strip() else new_block

    next_year_match = re.search(r"^\* \d{4}", content[year_pos + len(year_header):], re.MULTILINE)
    if next_year_match:
        year_end_pos = year_pos + len(year_header) + next_year_match.start()
    else:
        year_end_pos = len(content)

    year_section = content[year_pos:year_end_pos]

    month_pos_in_year = year_section.find(month_header)
    if month_pos_in_year == -1:
        first_newline = year_section.find("\n")
        insert_at = year_pos + (first_newline + 1 if first_newline != -1 else len(year_header))
        month_block = f"{month_header}\n{day_block}"
        return content[:insert_at] + month_block + content[insert_at:]

    abs_month_pos = year_pos + month_pos_in_year

    next_sub_match = re.search(r"^\*\*? ", year_section[month_pos_in_year + len(month_header):], re.MULTILINE)
    if next_sub_match:
        abs_month_end_pos = abs_month_pos + len(month_header) + next_sub_match.start()
    else:
        abs_month_end_pos = year_end_pos

    month_header_end = content.find("\n", abs_month_pos)
    if month_header_end == -1 or month_header_end > abs_month_end_pos:
        month_header_end = abs_month_pos + len(month_header)

    return content[:month_header_end + 1] + day_block + content[month_header_end + 1:]


def finalize_day_end(content, date_info, logs_dir, args):
    dt, year_str, month_name, day_name, date_formatted, short_day, day_header_str = date_info

    if day_header_str not in content:
        print(f"Error: Entry for {date_formatted} not found in org file.")
        return content

    pattern = re.escape(day_header_str) + r"(.*?)(?=\n\*\*\* <|\n\* |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print(f"Error: Could not isolate day block for {date_formatted}.")
        return content

    day_block = match.group(0)

    # 1. Calculate Goals %
    todo_matches = re.findall(r"^\*+\s+(TODO|DONEFORTODAY|DONE|FAILED)\s+(.+)$", day_block, re.MULTILINE)
    total_goals = len(todo_matches)
    done_goals = sum(1 for status, text in todo_matches if status in ("DONE", "DONEFORTODAY"))
    goals_pct = round((done_goals / total_goals) * 100) if total_goals > 0 else 0

    # 2. Process Food Log
    food_log_filename = f"food-log-{date_formatted}.json"
    food_log_path = os.path.join(logs_dir, food_log_filename)
    food_data = load_json_file(food_log_path)

    food_kcal_intake = 0.0
    food_lines = []
    if food_data:
        meals = food_data.get("meals", [])
        for m in meals:
            m_name = m.get("meal_name", "Meal")
            m_kcal = m.get("calories_kcal", 0.0)
            food_lines.append(f"     - {m_name} ({m_kcal:.0f}kCal)")
        if "total" in food_data and "calories_kcal" in food_data["total"]:
            food_kcal_intake = food_data["total"]["calories_kcal"]
        else:
            food_kcal_intake = sum(m.get("calories_kcal", 0.0) for m in meals)

    # 3. Process Workout Log
    workout_log_filename = f"workout-log-{date_formatted}.json"
    workout_log_path = os.path.join(logs_dir, workout_log_filename)
    workout_data = load_json_file(workout_log_path)

    workout_kcal_burn = 0.0
    workout_duration_min = 0
    workout_lines = []
    log_weight_kg = None
    log_steps = None
    bmr_kcal = DEFAULT_FALLBACK_BMR_KCAL

    if workout_data:
        athlete = workout_data.get("athlete", {})
        log_weight_kg = athlete.get("weight_kg")
        if athlete.get("bmr_kcal") is not None:
            bmr_kcal = float(athlete.get("bmr_kcal"))

        log_steps = workout_data.get("daily_step_count")

        workouts_list = workout_data.get("workouts", [])
        for w in workouts_list:
            w_type = w.get("type", "workout")
            w_dur = w.get("duration_minutes", 0)
            workout_duration_min += w_dur
            est_burn = w.get("estimated_calorie_burn", {})
            w_kcal = est_burn.get("gross_kcal", est_burn.get("net_kcal", 0))
            workout_lines.append(f"     - {w_type} ({w_dur} min, {w_kcal} kCal)")

        total_active = workout_data.get("total_daily_active_calories", {})
        workout_kcal_burn = total_active.get("gross_total_kcal", 0.0)
        if not workout_kcal_burn:
            workout_kcal_burn = sum(w.get("estimated_calorie_burn", {}).get("gross_kcal", 0) for w in workouts_list)

    # 4. Calorie Balance calculation: Intake - (Active Workout Burn + BMR from workout log)
    total_expenditure = workout_kcal_burn + bmr_kcal
    kcal_balance = round(food_kcal_intake - total_expenditure)

    # 5. Telemetry Inputs
    kg_val = args.kg if args.kg is not None else (log_weight_kg if log_weight_kg is not None else 0.0)
    tobacco_val = args.tobacco if args.tobacco is not None else 0
    km_val = args.km_driven if args.km_driven is not None else 0.0
    steps_val = args.steps if args.steps is not None else (log_steps if log_steps is not None else 0)
    sleep_val = args.sleep_hrs if args.sleep_hrs is not None else 0.0

    if sys.stdin.isatty():
        print(f"\n--- Entering Telemetry Data for {date_formatted} ---")
        try:
            if args.kg is None and log_weight_kg is None:
                inp = input("Weight (Kg): ").strip()
                if inp: kg_val = float(inp)
            if args.tobacco is None:
                inp = input("Tobacco units: ").strip()
                if inp: tobacco_val = int(inp)
            if args.km_driven is None:
                inp = input("Km driven: ").strip()
                if inp: km_val = float(inp)
            if args.steps is None and log_steps is None:
                inp = input("Steps count: ").strip()
                if inp: steps_val = int(inp)
            if args.sleep_hrs is None:
                inp = input("Sleep (hrs): ").strip()
                if inp: sleep_val = float(inp)
        except ValueError as e:
            print(f"Input error: {e}. Falling back to default values.")

    # 6. Reconstruct Day Block
    food_header = f"**** Food [{food_kcal_intake:.0f}kCal]"
    food_section_content = food_header + "\n" + "\n".join(food_lines) if food_lines else food_header

    workout_header = f"**** Workout [{workout_kcal_burn:.0f}kCal]"
    workout_section_content = workout_header + "\n" + "\n".join(workout_lines) if workout_lines else workout_header

    day_block = re.sub(r"\*\*\*\* Food.*?(?=\n\*\*\*\* |\Z)", food_section_content, day_block, flags=re.DOTALL)
    day_block = re.sub(r"\*\*\*\* Workout.*?(?=\n\*\*\*\* |\Z)", workout_section_content, day_block, flags=re.DOTALL)

    stat_table_str = (
        "**** Stat table\n"
        "     |------+---------+-----------+-------+-----------+-------------+---------+--------------|\n"
        "     |   Kg | Tobacco | Km driven | Steps | Sleep hrs | Workout min | Goals % | kCal balance |\n"
        "     |------+---------+-----------+-------+-----------+-------------+---------+--------------|\n"
        f"     | {kg_val:4.1f} | {tobacco_val:7d} | {km_val:9.1f} | {steps_val:5d} | {sleep_val:9.1f} | {workout_duration_min:11d} | {goals_pct:7d} | {kcal_balance:12d} |\n"
        "     |------+---------+-----------+-------+-----------+-------------+---------+--------------|"
    )

    day_block = re.sub(r"\*\*\*\* Stat table.*?(?=\n\*\*\* <|\n\* |\Z)", stat_table_str, day_block, flags=re.DOTALL)
    content = content[:match.start()] + day_block + content[match.end():]
    return content


def main():
    args = parse_args()
    date_info = get_date_info(args.date)

    org_file_path = args.file
    if not os.path.exists(org_file_path):
        parent_dir = os.path.dirname(org_file_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        print(f"Org file '{org_file_path}' not found. Creating a new org file.")
        content = DEFAULT_ORG_HEADER
    else:
        with open(org_file_path, "r", encoding="utf-8") as f:
            content = f.read()

    if args.day_start:
        daily_sched_path = os.path.join(args.schedules_dir, "daily-schedule.json")
        weekly_sched_path = os.path.join(args.schedules_dir, "weekly-schedule.json")

        daily_sched = load_json_file(daily_sched_path)
        if not daily_sched:
            daily_sched = load_json_file("/workspace/knowledge/daily-schedule.json.txt") or {}

        weekly_sched = load_json_file(weekly_sched_path)
        if not weekly_sched:
            weekly_sched = load_json_file("/workspace/knowledge/weekly-schedule.json.txt") or {}

        rollovers = find_previous_day_rollovers(content, date_info[4])
        if rollovers:
            print(f"  Rolled over {len(rollovers)} task(s) from previous day: {', '.join(rollovers)}")

        day_block = build_day_start_block(date_info, daily_sched, weekly_sched, rollovers)
        new_content = insert_day_start_into_org(content, day_block, date_info, force=args.force)

        with open(org_file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"✓ Day-start initialized for {date_info[4]} ({date_info[3]}) in '{org_file_path}'.")

    elif args.day_end:
        new_content = finalize_day_end(content, date_info, args.logs_dir, args)
        with open(org_file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"✓ Day-end stats & calorie balance calculated for {date_info[4]} in '{org_file_path}'.")


if __name__ == "__main__":
    main()
