from collections import defaultdict
from django.db.models import Max
import pulp
import logging
from .models import Teacher, Subject, Division, Preference

logger = logging.getLogger(__name__)

def get_teacher_subject_division_mapping(require_preference=False,
                                         preference_missing_score=0,
                                         solver_time_limit=None):
    """
    Builds and solves an ILP to maximize teacher satisfaction.

    Parameters:
    - require_preference: if True, only allow assignments where a Preference row exists.
                          if False, allow assignment with preference_missing_score.
    - preference_missing_score: score used when Preference is missing and require_preference is False.
    - solver_time_limit: seconds to limit solver (None means no time limit).

    Returns:
    dict containing:
      - 'assignments': list of (teacher_id, subject_id, division_id)
      - 'teacher_stats': {teacher_id: {'workload': float, 'unused_capacity': float, 'max_workload': int}}
      - 'subject_stats': {subject_id: {'hours_needed', 'hours_assigned', 'shortage', 'unused_capacity', 'teachers_assigned_count', 'divisions_needed'}}
      - 'total_satisfaction': float
      - 'objective_value': float
      - 'top_shortages': list of (subject_id, shortage_hours)
      - 'top_unused_capacity': list of (subject_id, unused_capacity_hours)
      - 'solver_status': str
      - 'infeasibility_reasons': list of str (if infeasible)
    """

    # --- Load data from DB ---
    teachers = list(Teacher.objects.select_related('department').all())
    subjects = list(Subject.objects.all())
    divisions = list(Division.objects.prefetch_related('subjects').all())

    # Build list of (subject, division) pairs
    subj_div_pairs = []
    for d in divisions:
        for s in d.subjects.all():
            subj_div_pairs.append((s, d))

    # Map IDs to objects and indices
    teacher_idx = {t.id: i for i, t in enumerate(teachers)}
    subject_idx = {s.id: i for i, s in enumerate(subjects)}
    division_idx = {d.id: i for i, d in enumerate(divisions)}

    # Precompute hours per subject (lecture=1h, lab=2h)
    hours_per_subject = {s.id: s.lectures_per_week + 2 * s.labs_per_week for s in subjects}

    # Preferences: dict (teacher_id, subject_id) -> (score, created_ts_seconds)
    prefs_qs = Preference.objects.all()
    max_created = prefs_qs.aggregate(Max('created_at'))['created_at__max']
    max_created_ts = max_created.timestamp() if max_created else 0.0

    pref_map = {(p.teacher_id, p.subject_id): (p.score, p.created_at.timestamp()) for p in prefs_qs}

    # Allowed teachers per subject
    allowed_teachers_for_subject = defaultdict(list)
    for s in subjects:
        for t in teachers:
            key = (t.id, s.id)
            if not require_preference or key in pref_map:
                allowed_teachers_for_subject[s.id].append(t)

    # --- Infeasibility Check ---
    infeasibility_reasons = []
    total_required_hours = 0
    subject_division_demand = defaultdict(float)
    for s, d in subj_div_pairs:
        subject_division_demand[(s.id, d.id)] = hours_per_subject[s.id]
        total_required_hours += hours_per_subject[s.id]
        if len(allowed_teachers_for_subject[s.id]) == 0:
            infeasibility_reasons.append(
                f"No available teachers for subject {s.id} (name: {s.name}) in division {d.id} (name: {d.name})"
            )

    total_available_hours = sum(t.max_workload for t in teachers)
    if total_available_hours < total_required_hours:
        infeasibility_reasons.append(
            f"Total teacher capacity ({total_available_hours} hours) is less than required ({total_required_hours} hours)"
        )

    logger.debug(f"Total required hours: {total_required_hours}, Total available hours: {total_available_hours}")
    logger.debug(f"Subject-division pairs: {len(subj_div_pairs)}, Teachers: {len(teachers)}")

    # Compute subject stats for infeasible cases
    subject_stats = {}
    total_divisions_per_subject = defaultdict(int)
    for s, d in subj_div_pairs:
        total_divisions_per_subject[s.id] += 1

    for s in subjects:
        hours_needed = hours_per_subject[s.id] * total_divisions_per_subject.get(s.id, 0)
        hours_available = sum(t.max_workload for t in allowed_teachers_for_subject[s.id])
        shortage = max(0.0, hours_needed - hours_available)
        unused_capacity = max(0.0, hours_available - hours_needed)
        subject_stats[s.id] = {
            'hours_needed': float(hours_needed),
            'hours_assigned': 0.0,
            'shortage': float(shortage),
            'unused_capacity': float(unused_capacity),
            'teachers_assigned_count': 0,
            'divisions_needed': total_divisions_per_subject.get(s.id, 0)
        }

    if infeasibility_reasons:
        shortages = [(s_id, st['shortage']) for s_id, st in subject_stats.items() if st['shortage'] > 0]
        shortages.sort(key=lambda x: -x[1])
        unused_capacities = [(s_id, st['unused_capacity']) for s_id, st in subject_stats.items() if st['unused_capacity'] > 0]
        unused_capacities.sort(key=lambda x: -x[1])
        return {
            'solver_status': 'infeasible',
            'infeasibility_reasons': infeasibility_reasons,
            'subject_stats': subject_stats,
            'top_shortages': shortages[:10],
            'top_unused_capacity': unused_capacities[:10],
            'assignments': [],
            'teacher_stats': {t.id: {'workload': 0.0, 'unused_capacity': float(t.max_workload), 'max_workload': t.max_workload} for t in teachers},
            'total_satisfaction': 0.0,
            'objective_value': 0.0
        }

    # --- Build the LP ---
    prob = pulp.LpProblem("TeacherAssignment_MaxSatisfaction", pulp.LpMaximize)

    # Binary variables x_t_s_d
    x = {}
    for s, d in subj_div_pairs:
        for t in allowed_teachers_for_subject[s.id]:
            x[(t.id, s.id, d.id)] = pulp.LpVariable(f"x_t{t.id}_s{s.id}_d{d.id}", cat="Binary")

    # Workload variables
    workload = {t.id: pulp.LpVariable(f"workload_t{t.id}", lowBound=0, cat="Continuous") for t in teachers}
    max_used = pulp.LpVariable("max_workload_used", lowBound=0, cat="Continuous")

    # Constraints
    for s, d in subj_div_pairs:
        prob += (
            pulp.lpSum(x[(t.id, s.id, d.id)] for t in allowed_teachers_for_subject[s.id] if (t.id, s.id, d.id) in x) == 1,
            f"assign_s{s.id}_d{d.id}"
        )

    for t in teachers:
        terms = [hours_per_subject[s.id] * x[(t.id, s.id, d.id)] for s, d in subj_div_pairs if (t.id, s.id, d.id) in x]
        prob += (workload[t.id] == pulp.lpSum(terms)), f"workload_def_t{t.id}"
        prob += (workload[t.id] <= t.max_workload), f"max_workload_t{t.id}"
        prob += (max_used >= workload[t.id]), f"maxused_ge_workload_t{t.id}"

    # --- Objective ---
    total_score_terms = []
    priority_terms = []
    SCORE_WEIGHT = 1.0
    PRIORITY_EPS = 1e-3
    MAXWORK_PENALTY = 1e-4

    for (t_id, s_id, d_id), var in x.items():
        score_val = pref_map.get((t_id, s_id), (preference_missing_score, None))[0]
        created_ts = pref_map.get((t_id, s_id), (None, max_created_ts))[1]
        total_score_terms.append(score_val * var)
        priority = (max_created_ts - created_ts) / max_created_ts if max_created_ts else 0.0
        priority_terms.append(priority * var)

    prob += (
        SCORE_WEIGHT * pulp.lpSum(total_score_terms)
        + PRIORITY_EPS * pulp.lpSum(priority_terms)
        - MAXWORK_PENALTY * max_used
    ), "Maximize_Total_Satisfaction"

    # Solve
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=solver_time_limit) if solver_time_limit else pulp.PULP_CBC_CMD(msg=False)
    print("solving...")
    prob.solve(solver)
    status = pulp.LpStatus[prob.status]
    logger.debug(f"Solver status: {status}")

    # --- Parse Solution ---
    assignments = []
    teacher_workloads = {t.id: 0.0 for t in teachers}
    subject_hours_assigned = defaultdict(float)
    subject_teachers_assigned = defaultdict(set)
    total_satisfaction_val = 0.0

    for (t_id, s_id, d_id), var in x.items():
        if pulp.value(var) and pulp.value(var) > 0.5:
            assignments.append((t_id, s_id, d_id))
            hrs = hours_per_subject[s_id]
            teacher_workloads[t_id] += hrs
            subject_hours_assigned[s_id] += hrs
            subject_teachers_assigned[s_id].add(t_id)
            score_val = pref_map.get((t_id, s_id), (preference_missing_score, None))[0]
            total_satisfaction_val += score_val

    teacher_stats = {
        t.id: {
            'workload': float(teacher_workloads[t.id]),
            'unused_capacity': float(t.max_workload - teacher_workloads[t.id]),
            'max_workload': t.max_workload
        } for t in teachers
    }

    subject_stats = {}
    total_divisions_per_subject = defaultdict(int)
    for s, d in subj_div_pairs:
        total_divisions_per_subject[s.id] += 1

    for s in subjects:
        hours_needed = hours_per_subject[s.id] * total_divisions_per_subject.get(s.id, 0)
        hours_assigned = subject_hours_assigned.get(s.id, 0.0)
        hours_available = sum(t.max_workload for t in allowed_teachers_for_subject[s.id])
        shortage = max(0.0, hours_needed - hours_assigned)
        unused_capacity = max(0.0, hours_available - hours_assigned)
        subject_stats[s.id] = {
            'hours_needed': float(hours_needed),
            'hours_assigned': float(hours_assigned),
            'shortage': float(shortage),
            'unused_capacity': float(unused_capacity),
            'teachers_assigned_count': len(subject_teachers_assigned.get(s.id, set())),
            'divisions_needed': total_divisions_per_subject.get(s.id, 0)
        }

    shortages = [(s_id, st['shortage']) for s_id, st in subject_stats.items() if st['shortage'] > 0]
    shortages.sort(key=lambda x: -x[1])
    unused_capacities = [(s_id, st['unused_capacity']) for s_id, st in subject_stats.items() if st['unused_capacity'] > 0]
    unused_capacities.sort(key=lambda x: -x[1])

    objective_value = pulp.value(prob.objective) if prob.objective is not None else 0.0

    return {
        'assignments': assignments,
        'teacher_stats': teacher_stats,
        'subject_stats': subject_stats,
        'total_satisfaction': float(total_satisfaction_val),
        'objective_value': float(objective_value),
        'top_shortages': shortages[:10],
        'top_unused_capacity': unused_capacities[:10],
        'solver_status': status,
        'infeasibility_reasons': [] if status == "Optimal" else [f"Solver failed with status: {status}"]
    }