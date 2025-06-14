# Forms.py — All npyscreen Forms for Lifelog UI Modules

import npyscreen
from datetime import datetime
from lifelog.utils.goal_util import GoalKind, Period, get_description_for_goal_kind
from lifelog.utils.shared_utils import get_available_categories, get_available_projects, get_available_tags, validate_task_inputs, now_utc

# ---------- TASK FORMS ----------


class TaskForm(npyscreen.ActionFormV2):
    def create(self):
        # Use a scrollable Form if available
        if hasattr(self, 'lines') and self.lines < 20:
            npyscreen.notify_confirm(
                "Terminal too small for Add Task form! Please resize (min 20 rows).", title="UI Error")
            self.parentApp.setNextForm(None)
            return

        self.add(npyscreen.FixedText, value="Fields marked * are required.",
                 color="CAUTION", editable=False)
        self.title = self.add(npyscreen.TitleText,
                              name="Title*", value="", begin_entry_at=18)
        # CATEGORY
        self.category = self.add(
            npyscreen.TitleText, name="Category (optional):", begin_entry_at=18)
        self.category_select_btn = self.add(
            npyscreen.ButtonPress, name="[Select Category]", when_pressed_function=self.select_category
        )
        # PROJECT
        self.project = self.add(npyscreen.TitleText,
                                name="Project (optional):", begin_entry_at=18)
        self.project_select_btn = self.add(
            npyscreen.ButtonPress, name="[Select Project]", when_pressed_function=self.select_project
        )

        self.due = self.add(npyscreen.TitleText,
                            name="Due (YYYY-MM-DD or 1d):", begin_entry_at=18)
        self.importance = self.add(
            npyscreen.TitleCombo,
            name="Importance (1-5):",
            values=["1", "2", "3", "4", "5"],
            value="2",  # Default to medium
            begin_entry_at=18
        )
        self.notes = self.add(npyscreen.TitleMultiLine,
                              name="Notes:", max_height=5)
        # TAGS (multi-select)
        self.tags = self.add(npyscreen.TitleText,
                             name="Tags (comma, optional):", begin_entry_at=18)
        self.tags_select_btn = self.add(
            npyscreen.ButtonPress, name="[Select Tags]", when_pressed_function=self.select_tags
        )
        self.recur_enabled = self.add(
            npyscreen.TitleSelectOne,
            name="Repeat?",
            values=["No", "Yes"],
            scroll_exit=True,
            max_height=2,  # 2 is enough for Yes/No
        )
        self.recur_everyX = self.add(
            npyscreen.TitleText, name="Repeat every X:", value="1", begin_entry_at=18)
        self.recur_unit = self.add(npyscreen.TitleCombo, name="Unit:", values=[
                                   "day", "week", "month", "year"], begin_entry_at=18)
        self.recur_days = self.add(
            npyscreen.TitleText, name="Days of week (0=Mon,6=Sun):", begin_entry_at=30)
        self.recur_first_of_month = self.add(
            npyscreen.TitleSelectOne,
            name="First of Month?",
            values=["No", "Yes"],
            scroll_exit=True,
            max_height=2,
        )
        self.recur_fields = [self.recur_everyX, self.recur_unit,
                             self.recur_days, self.recur_first_of_month]

        # Hide recurrence fields by default
        for fld in self.recur_fields:
            fld.hidden = True

    def select_category(self):
        cats = get_available_categories()
        if not cats:
            npyscreen.notify_confirm(
                "No categories available. Type to add new.", title="Category")
            return
        sel = npyscreen.selectOne(cats, title="Select Category")
        if sel:
            self.category.value = cats[sel[0]]

    def select_project(self):
        projects = get_available_projects()
        if not projects:
            npyscreen.notify_confirm(
                "No projects available. Type to add new.", title="Project")
            return
        sel = npyscreen.selectOne(projects, title="Select Project")
        if sel:
            self.project.value = projects[sel[0]]

    def select_tags(self):
        tags = get_available_tags()
        if not tags:
            npyscreen.notify_confirm(
                "No tags in config. Type to add new.", title="Tags")
            return
        sel = npyscreen.selectMultiple(
            tags, title="Select Tags (space to pick, Enter to confirm)")
        if sel:
            selected_tags = [tags[i] for i in sel]
            # Merge with any tags user already typed
            manual = [t.strip()
                      for t in self.tags.value.split(",") if t.strip()]
            final_tags = list(sorted(set(selected_tags + manual)))
            self.tags.value = ", ".join(final_tags)

    def while_editing(self, *args, **kwargs):
        show = self.recur_enabled.get_selected_objects(
        ) and self.recur_enabled.get_selected_objects()[0] == "Yes"
        for fld in self.recur_fields:
            fld.hidden = not show
        self.display()

    def on_ok(self):
        try:
            input_data = {}
            # Title
            input_data["title"] = self.title.value.strip()
            # Category/project
            input_data["category"] = self.category.value.strip() or None
            input_data["project"] = self.project.value.strip() or None
            # Due
            due_str = self.due.value.strip()
            input_data["due"] = due_str or None

            # Importance: read from TitleCombo index
            if isinstance(self.importance.value, int):
                idx = self.importance.value
                # guard index range
                if 0 <= idx < len(self.importance.values):
                    importance_str = self.importance.values[idx]
                    try:
                        importance = int(importance_str)
                    except:
                        raise ValueError(
                            f"Invalid importance: {importance_str}")
                else:
                    raise ValueError(
                        f"Importance selection out of range: {idx}")
            else:
                # fallback if value somehow a string
                importance = int(self.importance.value)
            input_data["importance"] = importance

            # Notes
            if hasattr(self.notes, "values"):
                input_data["notes"] = "\n".join(
                    self.notes.values).strip() or None
            else:
                input_data["notes"] = self.notes.value.strip() or None

            # Tags
            tags_str = (self.tags.value or "").strip()
            input_data["tags"] = tags_str or None

            # Validate required
            validate_task_inputs(
                title=input_data["title"],
                importance=input_data["importance"]
            )

            # Recurrence block
            if (self.recur_enabled.get_selected_objects() and
                    self.recur_enabled.get_selected_objects()[0] == "Yes"):
                # everyX
                everyX_val = self.recur_everyX.value.strip()
                if not everyX_val:
                    raise ValueError(
                        "Recurrence: 'every X' is required if repeating")
                try:
                    everyX = int(everyX_val)
                except:
                    raise ValueError(
                        f"Invalid recurrence everyX: {everyX_val}")

                # unit: read from TitleCombo index
                if isinstance(self.recur_unit.value, int):
                    idx_u = self.recur_unit.value
                    if 0 <= idx_u < len(self.recur_unit.values):
                        unit = self.recur_unit.values[idx_u]
                    else:
                        raise ValueError(
                            f"Invalid recurrence unit selection: {idx_u}")
                else:
                    unit = self.recur_unit.value.strip()

                # daysOfWeek
                days_val = (self.recur_days.value or "").strip()
                if days_val:
                    try:
                        daysOfWeek = [int(d) for d in days_val.split(
                            ",") if d.strip() != ""]
                    except:
                        raise ValueError(
                            f"Invalid recurrence days: {days_val}")
                else:
                    daysOfWeek = []

                # onFirstOfMonth
                onFirst = False
                if (self.recur_first_of_month.get_selected_objects() and
                        self.recur_first_of_month.get_selected_objects()[0] == "Yes"):
                    onFirst = True

                input_data["recurrence"] = {
                    "repeat": True,
                    "everyX": everyX,
                    "unit": unit,
                    "daysOfWeek": daysOfWeek,
                    "onFirstOfMonth": onFirst,
                    "baseDueTime": now_utc().isoformat(),
                    "lastCreated": now_utc().isoformat(),
                }
            else:
                input_data["recurrence"] = None

            # Pass back
            self.parentApp.form_data = input_data
            self.parentApp.setNextForm(None)
        except Exception as e:
            npyscreen.notify_confirm(str(e), title="Error")
            return

    def on_cancel(self):
        self.parentApp.form_data = None
        self.parentApp.setNextForm(None)


class TaskCloneForm(TaskForm):
    def create(self):
        self.SHOW_SCROLLBAR = True
        super().create()
        # Hide or disable fields not relevant for cloning (e.g., no status/time fields)


class TaskEditForm(TaskForm):
    def create(self):
        self.SHOW_SCROLLBAR = True
        super().create()
        # Allow editing everything except system fields (ID, created, etc)


class TaskViewForm(TaskForm):
    def create(self):
        self.SHOW_SCROLLBAR = True
        super().create()
        # After super().create(), set all widgets to editable=False
        for w in self._widgets__:
            w.editable = False

# ---------- TIME ENTRY FORMS ----------


class TimeEntryForm(npyscreen.ActionFormV2):
    def create(self):
        self.SHOW_SCROLLBAR = True
        self.add(npyscreen.FixedText, value="Log a manual time entry. * = required",
                 color="CAUTION", editable=False)
        self.title = self.add(npyscreen.TitleText,
                              name="Title*", value="", begin_entry_at=18)
        self.category = self.add(npyscreen.TitleCombo,
                                 name="Category", values=[], begin_entry_at=18)
        self.project = self.add(npyscreen.TitleCombo,
                                name="Project", values=[], begin_entry_at=18)
        self.tags = self.add(npyscreen.TitleText,
                             name="Tags (comma, optional):", begin_entry_at=18)
        self.notes = self.add(npyscreen.TitleMultiLine,
                              name="Notes (optional):", max_height=5)
        self.task_id = self.add(
            npyscreen.TitleText, name="Attach to Task ID [optional]:", begin_entry_at=28)
        self.start = self.add(
            npyscreen.TitleText, name="Start time (YYYY-MM-DD HH:MM or '1h ago'):", begin_entry_at=38)
        self.end = self.add(
            npyscreen.TitleText, name="End time (YYYY-MM-DD HH:MM or 'now'):", begin_entry_at=38)
        self.distracted = self.add(
            npyscreen.TitleText, name="Distracted minutes [optional]:", begin_entry_at=38)

    def on_ok(self):
        try:
            data = {
                "title": self.title.value.strip(),
                "category": self.category.value or None,
                "project": self.project.value or None,
                "tags": self.tags.value or None,
                "notes": "\n".join(self.notes.values) if hasattr(self.notes, "values") else self.notes.value,
                "task_id": int(self.task_id.value) if self.task_id.value else None,
                "start": self.start.value.strip(),
                "end": self.end.value.strip(),
                "distracted": float(self.distracted.value) if self.distracted.value else 0
            }
            self.parentApp.form_data = data
            self.parentApp.setNextForm(None)
        except Exception as e:
            npyscreen.notify_confirm(str(e), title="Error")

    def on_cancel(self):
        self.parentApp.form_data = None
        self.parentApp.setNextForm(None)

# ---------- TRACKER FORMS ----------


class TrackerForm(npyscreen.ActionFormV2):
    def create(self):
        self.SHOW_SCROLLBAR = True
        self.title = self.add(
            npyscreen.TitleText, name="Tracker Title*", value="", begin_entry_at=18)
        self.type = self.add(npyscreen.TitleCombo, name="Type*",
                             values=["int", "float", "bool", "str"], begin_entry_at=18)
        self.category = self.add(npyscreen.TitleCombo,
                                 name="Category", values=[], begin_entry_at=18)
        self.tags = self.add(npyscreen.TitleText,
                             name="Tags (comma, optional):", begin_entry_at=18)
        self.notes = self.add(npyscreen.TitleMultiLine,
                              name="Notes (optional):", max_height=4)
        # For tracker goals: ask after tracker creation

    def on_ok(self):
        try:
            data = {
                "title": self.title.value.strip(),
                "type": self.type.value or "int",
                "category": self.category.value or None,
                "tags": self.tags.value or None,
                "notes": "\n".join(self.notes.values) if hasattr(self.notes, "values") else self.notes.value
            }
            self.parentApp.form_data = data
            self.parentApp.setNextForm(None)
        except Exception as e:
            npyscreen.notify_confirm(str(e), title="Error")

    def on_cancel(self):
        self.parentApp.form_data = None
        self.parentApp.setNextForm(None)


class TrackerEntryForm(npyscreen.ActionFormV2):
    def create(self):
        self.SHOW_SCROLLBAR = True
        self.tracker_title = self.add(
            npyscreen.FixedText, value="(tracker info here)", editable=False)
        self.value = self.add(npyscreen.TitleText,
                              name="Value*", value="", begin_entry_at=12)
        self.timestamp = self.add(
            npyscreen.TitleText, name="Timestamp (YYYY-MM-DD HH:MM, blank=now):", begin_entry_at=42)

    def on_ok(self):
        try:
            self.parentApp.form_data = {
                "value": self.value.value.strip(),
                "timestamp": self.timestamp.value.strip()
            }
            self.parentApp.setNextForm(None)
        except Exception as e:
            npyscreen.notify_confirm(str(e), title="Error")

    def on_cancel(self):
        self.parentApp.form_data = None
        self.parentApp.setNextForm(None)

# ---------- GOAL FORM ----------


class GoalKindSelectForm(npyscreen.ActionFormV2):
    def create(self):
        self.SHOW_SCROLLBAR = True
        self.kind = self.add(
            npyscreen.TitleSelectOne,
            name="Select Goal Type*:",
            values=[
                f"{k.value}: {get_description_for_goal_kind(k)}" for k in GoalKind],
            scroll_exit=True,
            max_height=len(GoalKind)+2
        )
        self.description = self.add(
            npyscreen.FixedText, value="Choose a goal type to see description.", editable=False
        )

    def while_editing(self, *args, **kwargs):
        sel = self.kind.get_selected_objects()
        if sel:
            description = sel[0].split(
                ":", 1)[1].strip() if ":" in sel[0] else ""
            self.description.value = description
        self.display()

    def on_ok(self):
        sel = self.kind.get_selected_objects()
        if sel:
            kind_val = sel[0].split(":", 1)[0].strip()
            self.parentApp.goal_kind = kind_val
            self.parentApp.setNextForm("GOALDETAIL")
        else:
            npyscreen.notify_confirm(
                "Please select a goal kind.", title="Goal Type Required")

    def on_cancel(self):
        self.parentApp.goal_kind = None
        self.parentApp.setNextForm(None)


class GoalDetailForm(npyscreen.ActionFormV2):
    def create(self):
        self.SHOW_SCROLLBAR = True
        self.add(npyscreen.FixedText, value="Set Goal Details (* = required)",
                 color="CAUTION", editable=False)
        self.title = self.add(npyscreen.TitleText,
                              name="Goal Title*", value="", begin_entry_at=18)
        self.period = self.add(
            npyscreen.TitleCombo,
            name="Period*",
            values=[p.value for p in Period],
            value=0,
            begin_entry_at=18
        )
        # All possible fields (hidden as needed)
        self.amount = self.add(
            npyscreen.TitleText, name="Target Amount*", begin_entry_at=20, hidden=True)
        self.unit = self.add(npyscreen.TitleText, name="Unit",
                             begin_entry_at=12, hidden=True)
        self.min_amount = self.add(
            npyscreen.TitleText, name="Min Value*", begin_entry_at=18, hidden=True)
        self.max_amount = self.add(
            npyscreen.TitleText, name="Max Value*", begin_entry_at=18, hidden=True)
        self.mode = self.add(npyscreen.TitleText, name="Mode",
                             begin_entry_at=12, hidden=True)
        self.target = self.add(npyscreen.TitleText,
                               name="Target*", begin_entry_at=12, hidden=True)
        self.current = self.add(npyscreen.TitleText,
                                name="Current", begin_entry_at=12, hidden=True)
        self.target_streak = self.add(
            npyscreen.TitleText, name="Target Streak*", begin_entry_at=20, hidden=True)
        self.target_percentage = self.add(
            npyscreen.TitleText, name="Target %*", begin_entry_at=15, hidden=True)
        self.current_percentage = self.add(
            npyscreen.TitleText, name="Current %", begin_entry_at=15, hidden=True)
        self.old_behavior = self.add(
            npyscreen.TitleText, name="Old Behavior*", begin_entry_at=18, hidden=True)
        self.new_behavior = self.add(
            npyscreen.TitleText, name="New Behavior*", begin_entry_at=18, hidden=True)
        self.goal_help = self.add(
            npyscreen.FixedText, value="", color="CURSOR_INVERSE", editable=False)

    def beforeEditing(self):
        kind = getattr(self.parentApp, "goal_kind", None)
        if not kind:
            self.parentApp.setNextForm(None)
            return
        self.goal_kind = kind
        # Hide all
        for fld in [
            self.amount, self.unit, self.min_amount, self.max_amount, self.mode,
            self.target, self.current, self.target_streak, self.target_percentage,
            self.current_percentage, self.old_behavior, self.new_behavior
        ]:
            fld.hidden = True

        # Enable based on kind
        desc = get_description_for_goal_kind(GoalKind(kind))
        self.goal_help.value = f"About this goal: {desc}"

        if kind in ("sum", "count", "reduction", "duration"):
            self.amount.hidden = False
            self.unit.hidden = False
        if kind == "range":
            self.min_amount.hidden = False
            self.max_amount.hidden = False
            self.unit.hidden = False
            self.mode.hidden = False
        if kind == "milestone":
            self.target.hidden = False
            self.current.hidden = False
            self.unit.hidden = False
        if kind == "percentage":
            self.target_percentage.hidden = False
            self.current_percentage.hidden = False
        if kind == "streak":
            self.target_streak.hidden = False
        if kind == "replacement":
            self.old_behavior.hidden = False
            self.new_behavior.hidden = False
            self.amount.hidden = False
        self.display()

    def on_ok(self):
        try:
            kind = self.goal_kind
            period = self.period.values[self.period.value] if self.period.value is not None else None
            data = {
                "title": self.title.value.strip(),
                "kind": kind,
                "period": period,
            }
            # Collect values based on kind
            if kind in ("sum", "count", "reduction", "duration"):
                data["amount"] = float(
                    self.amount.value) if self.amount.value else None
                data["unit"] = self.unit.value
            if kind == "range":
                data["min_amount"] = float(
                    self.min_amount.value) if self.min_amount.value else None
                data["max_amount"] = float(
                    self.max_amount.value) if self.max_amount.value else None
                data["unit"] = self.unit.value
                data["mode"] = self.mode.value
            if kind == "milestone":
                data["target"] = float(
                    self.target.value) if self.target.value else None
                data["current"] = float(
                    self.current.value) if self.current.value else 0
                data["unit"] = self.unit.value
            if kind == "percentage":
                data["target_percentage"] = float(
                    self.target_percentage.value) if self.target_percentage.value else None
                data["current_percentage"] = float(
                    self.current_percentage.value) if self.current_percentage.value else 0
            if kind == "streak":
                data["target_streak"] = int(
                    self.target_streak.value) if self.target_streak.value else None
            if kind == "replacement":
                data["old_behavior"] = self.old_behavior.value
                data["new_behavior"] = self.new_behavior.value
                data["amount"] = float(
                    self.amount.value) if self.amount.value else 1

            if kind == "bool":
                data["amount"] = True

            self.parentApp.form_data = data
            self.parentApp.setNextForm(None)
        except Exception as e:
            npyscreen.notify_confirm(str(e), title="Error")

    def on_cancel(self):
        self.parentApp.form_data = None
        self.parentApp.setNextForm(None)


class LifelogGoalApp(npyscreen.NPSAppManaged):
    def onStart(self):
        self.addForm("GOALKIND", GoalKindSelectForm, name="Select Goal Type")
        self.addForm("GOALDETAIL", GoalDetailForm, name="Goal Details")
        self.goal_kind = None
        self.form_data = None


def run_goal_form_prefilled(goal=None):
    """
    Launch GoalDetailForm prefilled for editing; if goal=None, for adding.
    """
    class GoalEditApp(npyscreen.NPSAppManaged):
        def onStart(selfx):
            selfx.goal_kind = goal.kind if goal else None
            form = selfx.addForm("MAIN", GoalDetailForm, name="Goal Details")
            if goal:
                form.title.value = goal.get("title", "")
                period_val = goal.get("period", "")
                if period_val in [p.value for p in form.period.values]:
                    form.period.value = form.period.values.index(period_val)
                else:
                    form.period.value = 0
                # Fill in all possible fields (will be shown/hidden)
                form.amount.value = str(goal.get("amount") or "")
                form.unit.value = str(goal.get("unit") or "")
                form.min_amount.value = str(goal.get("min_amount") or "")
                form.max_amount.value = str(goal.get("max_amount") or "")
                form.mode.value = str(goal.get("mode") or "")
                form.target.value = str(goal.get("target") or "")
                form.current.value = str(goal.get("current") or "")
                form.target_streak.value = str(goal.get("target_streak") or "")
                form.target_percentage.value = str(
                    goal.get("target_percentage") or "")
                form.current_percentage.value = str(
                    goal.get("current_percentage") or "")
                form.old_behavior.value = str(goal.get("old_behavior") or "")
                form.new_behavior.value = str(goal.get("new_behavior") or "")
                form.display()
    app = GoalEditApp()
    app.run()
    return getattr(app, 'form_data', None)


def run_goal_form():
    app = LifelogGoalApp()
    app.setNextForm("GOALKIND")
    app.run()
    return app.form_data
# ---------------------
# Utility: You can create a helper App class to wrap each form.
# For example:


# Utility runner:
class LifelogFormApp(npyscreen.NPSAppManaged):
    def __init__(self, FormClass, *args, **kwargs):
        self._FormClass = FormClass
        super().__init__()

    def onStart(self):
        self.addForm("MAIN", self._FormClass, name=self._FormClass.__name__)
        self.form_data = None


def run_form(FormClass):
    app = LifelogFormApp(FormClass)
    app.run()
    return getattr(app, 'form_data', None)
