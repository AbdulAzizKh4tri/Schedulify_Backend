import math
from collections import defaultdict
from datetime import timezone

import pulp
from django.db.models import Max

from .models import Teacher, Subject, Division, Preference  # adjust import path


def get_teacher_subject_division_mapping(require_preference=False,
                                         preference_missing_score=0,
                                         solver_time_limit=None):
    """
    Builds and solves an ILP to maximize teacher satisfaction.

    Parameters:
    - require_preference: if True, only allow assignments where a Preference row exists.
                          if False, allow assignment but use preference_missing_score for score.
    - preference_missing_score: integer score used when Preference is missing and require_preference is False.
    - solver_time_limit: seconds to limit solver (None means no time limit).

    Returns:
    dict containing:
      - 'assignments': list of (teacher_id, subject_id, division_id)
      - 'teacher_stats': {teacher_id: {'workload': float, 'unused_capacity': float, 'max_workload': int}}
      - 'subject_stats': {subject_id: {'hours_needed', 'hours_assigned', 'shortage', 'teachers_assigned_count'}}
      - 'total_satisfaction': float
      - 'objective_value': float
      - 'top_shortages': list of (subject_id, shortage_hours)
      - 'top_overstaffed': list of (subject_id, overstaffed_hours)
      - 'solver_status': pulp.LpStatus[status_code]
    """

    # --- Load data from DB ---
    teachers = list(Teacher.objects.all())
    subjects = list(Subject.objects.all())
    divisions = list(Division.objects.prefetch_related('subjects').all())

    # Build list of (subject, division) pairs where the division requires the subject
    subj_div_pairs = []
    for d in divisions:
        for s in d.subjects.all():
            subj_div_pairs.append((s, d))

    # Map ids -> objects and indices
    teacher_idx = {t.id: i for i, t in enumerate(teachers)}
    idx_teacher = {i: t for t, i in teacher_idx.items()}  # not used often but handy
    subject_idx = {s.id: i for i, s in enumerate(subjects)}
    division_idx = {d.id: i for i, d in enumerate(divisions)}

    # Precompute hours per division for each subject (lecture=1h, lab=2h)
    hours_per_subject = {}
    for s in subjects:
        hours_per_subject[s.id] = s.lectures_per_week + 2 * s.labs_per_week

    # Preferences: dict (teacher_id, subject_id) -> (score, created_ts_seconds)
    prefs_qs = Preference.objects.all()
    # get max created_at for normalization (tie-break)
    max_created = prefs_qs.aggregate(Max('created_at'))['created_at__max']
    max_created_ts = max_created.timestamp() if max_created else 0.0

    pref_map = {}
    for p in prefs_qs:
        pref_map[(p.teacher_id, p.subject_id)] = (p.score, p.created_at.timestamp())

    # If require_preference=True, disallow assignments missing in pref_map
    # else allow, with preference_missing_score
    # Prepare list of allowed teachers for each subject (here: all teachers unless require_preference)
    allowed_teachers_for_subject = defaultdict(list)
    for s in subjects:
        for t in teachers:
            key = (t.id, s.id)
            if require_preference:
                if key in pref_map:
                    allowed_teachers_for_subject[s.id].append(t)
            else:
                allowed_teachers_for_subject[s.id].append(t)

    # Quick infeasibility check: if any (subject, division) has zero allowed teachers => infeasible
    for s, d in subj_div_pairs:
        if len(allowed_teachers_for_subject[s.id]) == 0:
            return {
                'error': f'No available teacher with preference for subject {s.id} in division {d.id}',
                'solver_status': 'infeasible_setup'
            }

    # --- Build the LP ---
    prob = pulp.LpProblem("TeacherAssignment_MaxSatisfaction", pulp.LpMaximize)

    # Create binary variables x_t_s_d
    x = {}  # (teacher_id, subject_id, division_id) -> pulp LpVariable
    for (s, d) in subj_div_pairs:
        for t in allowed_teachers_for_subject[s.id]:
            var_name = f"x_t{t.id}_s{s.id}_d{d.id}"
            x[(t.id, s.id, d.id)] = pulp.LpVariable(var_name, cat="Binary")

    # workload variables per teacher
    workload = {}
    for t in teachers:
        workload[t.id] = pulp.LpVariable(f"workload_t{t.id}", lowBound=0, cat="Continuous")

    # max_used variable (to weakly penalize high peaks)
    max_used = pulp.LpVariable("max_workload_used", lowBound=0, cat="Continuous")

    # Constraints:
    # 1) Each (subject, division) must be assigned to exactly one teacher
    for (s, d) in subj_div_pairs:
        vars_for_pair = []
        for t in allowed_teachers_for_subject[s.id]:
            key = (t.id, s.id, d.id)
            if key in x:
                vars_for_pair.append(x[key])
        # equality constraint
        prob += (pulp.lpSum(vars_for_pair) == 1), f"assign_s{s.id}_d{d.id}"

    # 2) workload[t] == sum_{s,d} hours[s] * x[t,s,d]
    for t in teachers:
        terms = []
        for (s, d) in subj_div_pairs:
            key = (t.id, s.id, d.id)
            if key in x:
                terms.append(hours_per_subject[s.id] * x[key])
        prob += (workload[t.id] == pulp.lpSum(terms)), f"workload_def_t{t.id}"

    # 3) workload constraint: workload[t] <= max_workload[t]
    for t in teachers:
        prob += (workload[t.id] <= t.max_workload), f"max_workload_t{t.id}"
        # link max_used >= workload[t]
        prob += (max_used >= workload[t.id]), f"maxused_ge_workload_t{t.id}"

    # --- Objective ---
    # Primary: sum score * x
    # Tie-break: tiny bonus based on created_at (older -> larger bonus)
    # Secondary: tiny penalty on max_used to encourage balanced peak workloads
    total_score_terms = []
    priority_terms = []

    # Scaling constants (tune if needed)
    SCORE_WEIGHT = 1.0  # primary
    PRIORITY_EPS = 1e-3  # small bonus for earlier created_at
    MAXWORK_PENALTY = 1e-4  # tiny penalty on max_used

    for (t_id, s_id, d_id), var in x.items():
        if (t_id, s_id) in pref_map:
            score_val, created_ts = pref_map[(t_id, s_id)]
        else:
            score_val = preference_missing_score
            created_ts = max_created_ts  # neutral; no bonus
        total_score_terms.append(score_val * var)

        # priority: older (smaller created_ts) -> larger (max_created_ts - created_ts)
        # Normalize by max_created_ts if >0
        if max_created_ts:
            priority = (max_created_ts - created_ts) / max_created_ts
        else:
            priority = 0.0
        priority_terms.append(priority * var)

    objective = (SCORE_WEIGHT * pulp.lpSum(total_score_terms)
                 + PRIORITY_EPS * pulp.lpSum(priority_terms)
                 - MAXWORK_PENALTY * max_used)

    prob += objective, "Maximize_Total_Satisfaction_with_tie_and_peak_penalty"

    # Solve
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=solver_time_limit) if solver_time_limit else pulp.PULP_CBC_CMD(msg=False)
    result_status = prob.solve(solver)

    status = pulp.LpStatus[prob.status]

    # If infeasible or not optimal, report status and return partial info
    if status not in ("Optimal", "Optimal (within gap)"):
        # attempt to return status and reason
        return {
            'solver_status': status,
            'message': 'Solver did not find optimal solution. Check constraints or increase solver time limit.'
        }

    # --- Parse solution ---
    assignments = []
    teacher_workloads = {t.id: 0.0 for t in teachers}
    subject_hours_assigned = defaultdict(float)
    subject_teachers_assigned = defaultdict(set)
    total_satisfaction_val = 0.0

    for (t_id, s_id, d_id), var in x.items():
        val = pulp.value(var)
        if val is not None and val > 0.5:
            assignments.append((t_id, s_id, d_id))
            hrs = hours_per_subject[s_id]
            teacher_workloads[t_id] += hrs
            subject_hours_assigned[s_id] += hrs
            subject_teachers_assigned[s_id].add(t_id)
            score_val = pref_map.get((t_id, s_id), (preference_missing_score, None))[0]
            total_satisfaction_val += score_val

    teacher_stats = {}
    for t in teachers:
        w = teacher_workloads[t.id]
        teacher_stats[t.id] = {
            'workload': float(w),
            'unused_capacity': float(t.max_workload - w),
            'max_workload': t.max_workload
        }

    # Subject stats
    subject_stats = {}
    total_divisions_per_subject = defaultdict(int)
    for (s, d) in subj_div_pairs:
        total_divisions_per_subject[s.id] += 1

    for s in subjects:
        hours_needed = hours_per_subject[s.id] * total_divisions_per_subject.get(s.id, 0)
        hours_assigned = subject_hours_assigned.get(s.id, 0.0)
        shortage = max(0.0, hours_needed - hours_assigned)
        overstaffed = max(0.0, hours_assigned - hours_needed)
        teachers_assigned_count = len(subject_teachers_assigned.get(s.id, set()))
        subject_stats[s.id] = {
            'hours_needed': float(hours_needed),
            'hours_assigned': float(hours_assigned),
            'shortage': float(shortage),
            'overstaffed': float(overstaffed),
            'teachers_assigned_count': teachers_assigned_count,
            'divisions_needed': total_divisions_per_subject.get(s.id, 0)
        }

    # Top shortages & overstaffed
    shortages = [(s_id, st['shortage']) for s_id, st in subject_stats.items() if st['shortage'] > 0]
    shortages.sort(key=lambda x: -x[1])
    overstaffed = [(s_id, st['overstaffed']) for s_id, st in subject_stats.items() if st['overstaffed'] > 0]
    overstaffed.sort(key=lambda x: -x[1])

    # objective_value (pulp)
    objective_value = pulp.value(prob.objective)

    return {
        'assignments': assignments,
        'teacher_stats': teacher_stats,
        'subject_stats': subject_stats,
        'total_satisfaction': float(total_satisfaction_val),
        'objective_value': float(objective_value),
        'top_shortages': shortages[:10],
        'top_overstaffed': overstaffed[:10],
        'solver_status': status
    }
